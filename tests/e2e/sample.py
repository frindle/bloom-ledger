#!/usr/bin/env python3
"""Fake data and small HTTP helpers shared by the end-to-end tests (CI only; nothing here is real provider data).

  sample.py home DIR                      write a fake Darkbloom folder (power minutes, earnings, provider log, usage ring)
  sample.py setup BASE USER PASSWORD COOKIEFILE SETUPCODE    create the admin through /v1/auth/setup (saves the session cookie)
  sample.py paircode BASE MACHINE COOKIEFILE       add a machine and print its one-time pairing code
  sample.py post BASE TOKEN               ship the fake data straight to /v1/objects as that machine
  sample.py wait BASE MACHINE SECONDS     wait until the ledger shows data from that machine
Python 3.9+, standard library only."""
import datetime as dt
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

POWER_COLS = ["ts_utc", "interval_s", "samples", "power_ok", "avg_w", "max_w", "wh", "dbk_up", "dbk_state",
              "inference_active_frac", "requests_delta", "tokens_delta", "warm_models", "load_transition_active",
              "gpu_pct", "other_work", "other_procs", "note"]


def utcnow():
    """Now, or the moment in SAMPLE_NOW (ISO, UTC). The upgrade test uses it: the previous release only keeps data dated after 2026-10-13."""
    raw = os.environ.get("SAMPLE_NOW", "")
    return dt.datetime.fromisoformat(raw).replace(tzinfo=dt.timezone.utc) if raw else dt.datetime.now(dt.timezone.utc)


def power_csv(days=3):
    """One row a minute for a few hours on each of the last `days` days, ending now."""
    now = utcnow().replace(second=0, microsecond=0)
    rows = [",".join(POWER_COLS)]
    for d in range(days):
        for m in range(0, 180, 1):
            ts = now - dt.timedelta(days=d, minutes=m)
            rows.append("%s,60,60,1,150,200,2.5,1,serving,0.5,1,10,m,0,50,0,," % ts.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return "\n".join(rows[:1] + sorted(rows[1:])) + "\n"


def earnings_jsonl(days=3):
    now = utcnow()
    out = []
    for d in range(days):
        for i in range(5):
            ts = now - dt.timedelta(days=d, hours=i + 1)
            out.append(json.dumps({"_id": "fake-%d-%d" % (d, i), "created_at": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                   "amount_micro_usd": 250000 + 1000 * i, "model": "fake-model", "job_id": "job-%d-%d" % (d, i)}))
    return "\n".join(out) + "\n"


def write_home(home):
    home = Path(home)
    (home / "power").mkdir(parents=True, exist_ok=True)
    (home / "earnings-archive").mkdir(parents=True, exist_ok=True)
    now = utcnow()
    (home / "power" / ("power-log-%s.csv" % now.strftime("%Y-%m"))).write_text(power_csv())
    (home / "earnings-archive" / "earnings.jsonl").write_text(earnings_jsonl())
    (home / "provider.log").write_text("".join("%s fake provider line %d\n" % (now.strftime("%Y-%m-%dT%H:%M:%SZ"), i) for i in range(5)))
    ring = [{"id": "fake-use-%d" % i, "completedAt": int(time.time()) - i * 60, "model": "fake-model"} for i in range(5)]
    (home / "usage-history.json").write_text(json.dumps(ring))


def object_bytes(kind, meta, payload):
    m = {"machine_id": "x", "kind": kind}
    m.update(meta)
    return json.dumps(m, sort_keys=True, separators=(",", ":")).encode() + b"\n" + payload.encode()


def req(base, method, path, obj=None, cookie_file=None, headers=None):
    h = {"Content-Type": "application/json", "Origin": base}
    if cookie_file and Path(cookie_file).exists():
        h["Cookie"] = Path(cookie_file).read_text().strip()
    h.update(headers or {})
    data = json.dumps(obj).encode() if obj is not None else None
    r = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}"), resp.headers
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"{}")
        except ValueError:
            body = {}
        return e.code, body, e.headers


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "home":
        write_home(argv[2])
    elif cmd == "setup":
        base, user, pw, cf, code = argv[2:7]
        st, body, hd = req(base, "POST", "/v1/auth/setup", {"username": user, "password": pw, "timezone": "America/Chicago", "rate": "0.15", "setup_code": code})
        if st != 200:
            sys.exit("setup failed: %s %s" % (st, body))
        Path(cf).write_text(hd.get("Set-Cookie", "").split(";", 1)[0] + "\n")
    elif cmd == "paircode":
        base, mid, cf = argv[2:5]
        st, body, _ = req(base, "POST", "/v1/settings/machines", {"id": mid}, cf)
        if st == 409:  # already added: same as Machines > New token
            st, body, _ = req(base, "POST", "/v1/settings/machines/rotate", {"id": mid}, cf)
        if st not in (200, 201) or "pair_code" not in body:
            sys.exit("add machine failed: %s %s" % (st, body))
        print(body["pair_code"])
    elif cmd == "post":
        base, token = argv[2:4]
        for kind, meta, payload in (("log", {"path": "power/power-log-%s.csv" % utcnow().strftime("%Y-%m"), "offset": 0}, power_csv()),
                                    ("log", {"path": "earnings-archive/earnings.jsonl", "offset": 0}, earnings_jsonl())):
            body = object_bytes(kind, meta, payload)
            r = urllib.request.Request(base + "/v1/objects", data=body, method="POST", headers={
                "Authorization": "Bearer " + token, "X-Bloom-Kind": kind, "X-Bloom-Sha256": hashlib.sha256(body).hexdigest(),
                "Content-Type": "application/octet-stream"})
            urllib.request.urlopen(r, timeout=20).read()
    elif cmd == "wait":
        base, mid, secs = argv[2], argv[3], int(argv[4])
        end = time.time() + secs
        last = ""
        while time.time() < end:
            try:
                st, status, _ = req(base, "GET", "/v1/status")
                _, series, _ = req(base, "GET", "/v1/earnings/series")
                mine = [m for m in status.get("machines", []) if m.get("id") == mid]
                last = "machine=%s series_total=%s" % (mine[0] if mine else None, series.get("total_micro"))
                if mine and mine[0].get("objects", 0) > 0 and series.get("total_micro", 0) > 0:
                    print("data arrived: %s" % last)
                    return
            except (OSError, ValueError) as e:
                last = str(e)
            time.sleep(5)
        sys.exit("no data from %s after %ds (%s)" % (mid, secs, last))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
