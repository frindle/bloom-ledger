"""Live status for the ledger page: Darkbloom serving state and Sandbox host state from Darkbloom's account API
(with a key the owner saves in Settings), plus this ledger's newest power minute (watts, Sandbox jobs) from the Mac.

The key is stored at <data>/secrets/darkbloom_api_key (mode 0600). It is never returned, logged or sent anywhere but
the allowlisted Darkbloom hosts over https. GET /v1/settings/darkbloom-key reports only whether it is set and what the
last check found."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_HOSTS = ("api.darkbloom.dev", "console.darkbloom.dev")
PROVIDERS_URL = "https://api.darkbloom.dev/v1/me/providers"
SANDBOX_HOSTS_URL = "https://console.darkbloom.dev/api/sandbox/hosts"
CACHE_S = 20
STALE_S = 180
_cache = {}


def key_path(root):
    return os.path.join(str(root), "secrets", "darkbloom_api_key")


def status_path(root):
    return os.path.join(str(root), "secrets", "darkbloom_api_key.status.json")


def read_key(root):
    try:
        with open(key_path(root)) as f:
            k = f.read().strip()
        return k or None
    except OSError:
        return None


def valid_key(k):
    return isinstance(k, str) and 8 <= len(k) <= 512 and k.isprintable() and not any(c.isspace() for c in k)


def _write_private(path, data):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(data)
    os.replace(tmp, path)


def http_get_json(url, key, timeout=10):
    """GET an allowlisted https URL with the key. Returns (status, json-or-None). Never raises; never echoes the key."""
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS:
        return (0, None)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (r.status, json.loads(r.read() or b"null"))
    except urllib.error.HTTPError as e:
        return (e.code, None)
    except Exception:
        return (0, None)


def probe(key, get=http_get_json):
    return {"darkbloom": get(PROVIDERS_URL, key)[0], "sandbox": get(SANDBOX_HOSTS_URL, key)[0]}


def key_post(root, body, now, get=http_get_json):
    """{"key": "<key>"} saves and checks it; {"key": null} removes it. Replies never include the key."""
    try:
        obj = json.loads(body or b"{}")
    except ValueError:
        return (400, {"error": "body must be JSON"})
    if not isinstance(obj, dict) or "key" not in obj:
        return (400, {"error": "send {\"key\": ...}"})
    k = obj["key"]
    if k is None:
        for p in (key_path(root), status_path(root)):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
        _cache.clear()
        return (200, key_status(root))
    k = k.strip() if isinstance(k, str) else k
    if not valid_key(k):
        return (400, {"error": "that doesn't look like an API key"})
    _write_private(key_path(root), k)
    _write_private(status_path(root), json.dumps({"checked_at": now, "probe": probe(k, get)}))
    _cache.clear()
    return (200, key_status(root))


def key_status(root):
    st = {}
    try:
        with open(status_path(root)) as f:
            st = json.load(f)
    except (OSError, ValueError):
        pass
    return {"set": read_key(root) is not None, "checked_at": st.get("checked_at"), "probe": st.get("probe")}


def _decode_tps(p):
    for slot in ((p.get("backend_capacity") or {}).get("slots") or []):
        pm = slot.get("performance_measurements") or {}
        for k in ("delivered_decode", "decode"):
            v = (pm.get(k) or {}).get("tokens_per_second")
            if isinstance(v, (int, float)):
                return round(v, 1)
    return None


def darkbloom_view(j):
    ps = (j or {}).get("providers") or []
    if not ps:
        return {"error": "no machines on this account"}
    out = []
    for p in ps:
        elig = p.get("routing_eligibility") or []
        cur = p.get("current_model")
        mine = next((e for e in elig if e.get("model") == cur), elig[0] if elig else {})
        m = p.get("system_metrics") or {}
        out.append({"name": p.get("nickname") or "machine",
                    "online": bool(p.get("online")), "status": p.get("status"), "last_heartbeat": p.get("last_heartbeat"),
                    "model": cur, "routing": mine.get("reason"), "pending": p.get("pending_requests"),
                    "max_concurrency": p.get("max_concurrency"), "decode_tps": _decode_tps(p),
                    "thermal": m.get("thermal_state"), "cpu": m.get("cpu_usage"), "memory": m.get("memory_pressure")})
    return {"machines": out}


def sandbox_view(j):
    hs = (j or {}).get("hosts") or []
    if not hs:
        return {"error": "no Sandbox host on this account"}
    return {"hosts": [{"name": h.get("name"), "online": bool(h.get("online")), "state": h.get("state"), "mode": h.get("mode"),
                       "running": h.get("current_runs")} for h in hs]}


def mac_view(db, now):
    """Newest power minute per machine, as the Mac reported it (about once a minute)."""
    rows = db.execute("SELECT p.machine_id, p.ts, p.wh, p.interval_s, p.dbk_state, p.sandbox_jobs"
                      " FROM power_minutes p JOIN (SELECT machine_id, MAX(ts) AS ts FROM power_minutes GROUP BY machine_id) n"
                      " ON p.machine_id = n.machine_id AND p.ts = n.ts ORDER BY p.machine_id").fetchall()
    out = []
    for mid, ts, wh, iv, dbk, sbx in rows:
        watts = round(wh * 3600 / iv, 1) if isinstance(wh, (int, float)) and iv else None
        out.append({"machine_id": mid, "ts": ts, "age_s": max(0, int(now - ts)), "stale": now - ts > STALE_S,
                    "watts": watts, "darkbloom_state": dbk, "sandbox_jobs": sbx})
    return out


def _remote(name, url, view, key, now, get):
    hit = _cache.get(name)
    if hit and now - hit[0] < CACHE_S:
        return hit[1]
    code, j = get(url, key)
    if code == 200:
        res = view(j)
    else:
        res = {"error": ("Darkbloom answered %s" % code) if code else "Darkbloom unreachable"}
    _cache[name] = (now, res)
    return res


def live(root, mac, now=None, get=http_get_json):
    """mac is mac_view()'s rows, read under the DB lock; the Darkbloom calls here run outside it."""
    now = time.time() if now is None else now
    key = read_key(root)
    res = {"at": now, "mac": mac}
    if key is None:
        res["darkbloom"] = {"error": "no API key saved"}
        res["sandbox"] = {"error": "no API key saved"}
    else:
        res["darkbloom"] = _remote("darkbloom", PROVIDERS_URL, darkbloom_view, key, now, get)
        res["sandbox"] = _remote("sandbox", SANDBOX_HOSTS_URL, sandbox_view, key, now, get)
    return res
