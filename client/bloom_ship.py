"""Ship the ledger spool to the Unraid ingest over LAN HTTP (stdlib only).

Each spool object is POSTed to <ingest>/v1/objects with a per-machine bearer token. The ingest stores it under
its sha256 (idempotent: a resend answers 200), so a crash between POST and move only causes one harmless resend.
Accepted objects move to ledger-spool/sent/<kind>/, permanently refused ones to ledger-spool/rejected/<kind>/.
A network failure or an auth refusal stops the run and backs off (30 s doubling to 15 min).
The token is never printed or logged. See the bloom-ledger README."""
import hashlib
import http.client
import ipaddress
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import bloom_archive as A

KEYCHAIN_SERVICE = "bloom-ledger-ingest"
OK_CODES = (200, 201)
AUTH_CODES = (401, 403)
REJECT_CODES = (400, 409, 413, 422)
BACKOFF_BASE_S = 30
BACKOFF_MAX_S = 900
RUN_LIMIT = 500
TIMEOUT_S = 30


def is_lan_url(url):
    """True only for http(s) URLs whose host is a literal private/loopback IP (no DNS, no public hosts)."""
    try:
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return False
        ip = ipaddress.ip_address(u.hostname)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def ingest_url(home, env=None):
    env = os.environ if env is None else env
    url = (env.get("BLOOM_INGEST_URL") or "").strip()
    if not url:
        try:
            url = str(json.loads((Path(home) / "ledger.json").read_text()).get("ingest_url") or "").strip()
        except (OSError, ValueError, AttributeError):
            url = ""
    return url


def keychain_token(machine_id, run=subprocess.run):
    """The machine's ingest token from the login Keychain, or "" (never raises, never logs the value)."""
    try:
        r = run(["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", machine_id, "-w"],
                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def post_object(url, token, path, kind, opener=urllib.request.urlopen):
    """POST one spool object. Returns "ok" | "reject" | "auth" | "retry"."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return "retry"
    sha = hashlib.sha256(data).hexdigest()
    if Path(path).name != sha + ".obj" or kind not in A.KINDS:
        return "reject"
    req = urllib.request.Request(
        url.rstrip("/") + "/v1/objects", data=data, method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "X-Bloom-Kind": kind,
            "X-Bloom-Sha256": sha,
            "Content-Type": "application/octet-stream",
        },
    )
    try:
        with opener(req, timeout=TIMEOUT_S) as resp:
            code = resp.status
    except urllib.error.HTTPError as e:
        code = e.code
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
        return "retry"
    if code in OK_CODES:
        return "ok"
    if code in AUTH_CODES:
        return "auth"
    if code in REJECT_CODES:
        return "reject"
    return "retry"


def next_backoff(fails):
    """Seconds to wait after `fails` consecutive failed runs."""
    if not fails or fails <= 0:
        return 0
    return min(BACKOFF_BASE_S * 2 ** min(fails - 1, 30), BACKOFF_MAX_S)


def move_to(spool, sub, kind, path):
    dest = Path(spool) / sub / kind
    dest.mkdir(parents=True, exist_ok=True)
    os.replace(path, dest / Path(path).name)


def pending(spool):
    """[(kind, path)] of every object waiting in spool/<kind>/, oldest first."""
    spool = Path(spool)
    if not spool.is_dir():
        return []
    result = []
    for kind in A.KINDS:
        kind_dir = spool / kind
        if not kind_dir.is_dir():
            continue
        for entry in kind_dir.iterdir():
            if entry.name.endswith('.obj') and not entry.name.startswith('.tmp-'):
                try:
                    st = entry.stat()
                    result.append((kind, entry, st.st_mtime_ns))
                except OSError:
                    continue
    result.sort(key=lambda t: (t[2], t[1].name))
    return [(t[0], t[1]) for t in result]


def ship_run(spool, url, token, state, now, opener=urllib.request.urlopen, limit=RUN_LIMIT):
    """One shipping pass. Updates state ({"fails", "next_try"}) in place; returns a summary dict."""
    res = {"ok": 0, "rejected": 0, "stopped": ""}
    if now < state.get("next_try", 0):
        res["stopped"] = "backoff"
        return res
    for kind, path in pending(spool)[:limit]:
        r = post_object(url, token, path, kind, opener)
        if r == "ok":
            move_to(spool, A.SENT_DIRNAME, kind, path)
            res["ok"] += 1
        elif r == "reject":
            move_to(spool, A.REJECTED_DIRNAME, kind, path)
            res["rejected"] += 1
        else:
            state["fails"] = state.get("fails", 0) + 1
            state["next_try"] = now + next_backoff(state["fails"])
            res["stopped"] = r
            return res
    state["fails"] = 0
    state["next_try"] = 0
    return res


def sha_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_state(spool):
    try:
        st = json.loads((Path(spool) / ".ship-state.json").read_text())
        return st if isinstance(st, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(spool, state):
    tmp = Path(spool) / ".ship-state.json.tmp"
    tmp.write_text(A.canonical(state))
    os.replace(tmp, Path(spool) / ".ship-state.json")
