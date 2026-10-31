#!/usr/bin/env python3
"""bloom-ledger ingest server (stdlib only). Runs in the Unraid container.

  POST /v1/objects   body = one spool object; headers Authorization: Bearer <machine token>, X-Bloom-Kind,
                     X-Bloom-Sha256. 201 stored, 200 already had it, 400/401/413/422 refused.
  GET  /healthz      200 {"ok": true, "objects": n} | 503
  GET  /v1/summary 200 {generated_at, machines: [per-machine day ribbon, last 90 UTC days]}  (metadata only)
  GET  /            the static dashboard page (dashboard.html)
  GET  /v1/alerts    200 [open alerts]  (machine silent > 30 min, ring snapshot > 12 h, OTS not upgraded in 48 h)

Background: every 10 min closes every finished UTC day since the last manifest (per machine, hash-chained,
OpenTimestamps-stamped); every 6 h runs `ots upgrade`; every 5 min evaluates alerts and, when the open set
changes, POSTs it to ALERT_WEBHOOK_URL (optional). Env: BLOOM_DATA (/data), BLOOM_TOKENS
(/run/secrets/bloom_tokens), BLOOM_PORT (8787), BLOOM_OTS_BIN (else `ots` on PATH), ALERT_WEBHOOK_URL.
Logs carry machine ids, counts and statuses only; never a token or a request body."""
import datetime as dt
import json
import os
import shutil
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bloom_alerts as AL  # noqa: E402
import bloom_ingest as I  # noqa: E402
import bloom_ingest_ledger as IL  # noqa: E402
import bloom_ledger as L  # noqa: E402
import bloom_settings as BS  # noqa: E402
import bloom_summary as SM  # noqa: E402

ROOT = Path(os.environ.get("BLOOM_DATA", "/data"))
TOKENS_PATH = os.environ.get("BLOOM_TOKENS", "/run/secrets/bloom_tokens")
PORT = int(os.environ.get("BLOOM_PORT", "8787"))
LISTEN = os.environ.get("BLOOM_LISTEN", "0.0.0.0")
OTS_BIN = os.environ.get("BLOOM_OTS_BIN") or shutil.which("ots")
WEBHOOK = os.environ.get("ALERT_WEBHOOK_URL", "")
DASHBOARD = Path(__file__).resolve().parent / "dashboard.html"
MACHINES_PATH = os.environ.get("BLOOM_MACHINES", str(ROOT / "machines.json"))
SETTINGS = Path(__file__).resolve().parent / "settings.html"
ADMIN_PATH = os.environ.get("BLOOM_ADMIN", "/run/secrets/bloom_admin")
DB_LOCK = threading.Lock()


def log(msg):
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}", flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "bloom-ledger/1"

    def log_message(self, fmt, *args):  # keep the access log free of headers; status + path only
        log(f"{self.address_string()} {fmt % args}")

    def reply(self, code, obj):
        data = json.dumps(obj, sort_keys=True).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            with DB_LOCK:
                self.reply(*I.healthz(ROOT, self.server.db))
        elif self.path == "/v1/summary":
            with DB_LOCK:
                self.reply(200, SM.summary(self.server.db, ROOT, time.time()))
        elif self.path in ("/", "/index.html"):
            data = DASHBOARD.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/v1/alerts":
            with DB_LOCK:
                self.reply(200, AL.evaluate_alerts(self.server.db, time.time()))
        elif self.path == "/settings":
            data = SETTINGS.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/v1/settings":
            with DB_LOCK:
                now = time.time()
                ids = sorted(set(I.load_tokens(TOKENS_PATH, MACHINES_PATH).values()))
                data = {
                    "admin_enabled": BS.admin_check({}, ADMIN_PATH)[0] != 403,
                    "machines": BS.machine_rows(self.server.db, ROOT, now, ids),
                    "health": BS.ledger_health(self.server.db, ROOT, now, self.server_version),
                }
                self.reply(200, data)
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/v1/objects":
            try:
                n = int(self.headers.get("Content-Length") or "-1")
            except ValueError:
                n = -1
            if n < 0:
                self.reply(411, {"error": "length required"})
                return
            if n > I.MAX_BYTES:
                self.reply(413, {"error": "too large"})
                self.close_connection = True
                return
            body = self.rfile.read(n)
            tokens = I.load_tokens(TOKENS_PATH, MACHINES_PATH)
            with DB_LOCK:
                code, obj = I.handle_post(self.headers, body, tokens, ROOT, self.server.db, time.time())
            self.reply(code, obj)
        elif self.path.startswith("/v1/settings/"):
            try:
                n = int(self.headers.get("Content-Length") or "-1")
            except ValueError:
                n = -1
            if n < 0:
                self.reply(411, {"error": "length required"})
                return
            if n > 4096:
                self.reply(413, {"error": "too large"})
                self.close_connection = True
                return
            body = self.rfile.read(n)
            with DB_LOCK:
                code, obj = BS.admin_post(self.path, self.headers, body, ADMIN_PATH, MACHINES_PATH, time.time())
            self.reply(code, obj)
        else:
            self.reply(404, {"error": "not found"})


def days_to_close(root, db, today):
    """Closed UTC days that still need a manifest for at least one machine, oldest first."""
    yesterday = (dt.date.fromisoformat(today) - dt.timedelta(days=1)).isoformat()
    starts = []
    for mid in IL.machines(db):
        have = [d for d, m in L.load_manifests(IL.ledger_dir(root, mid)) if m is not None]
        if have:
            starts.append(max(have))
        else:
            first = db.execute("SELECT MIN(day) FROM objects WHERE machine_id = ?", (mid,)).fetchone()[0]
            starts.append((dt.date.fromisoformat(first) - dt.timedelta(days=1)).isoformat())
    if not starts or min(starts) >= yesterday:
        return []
    return L.days_after(min(starts), yesterday)


def scheduler(db, stop):
    last_upgrade = 0.0
    last_alerts = None
    while not stop.wait(1):
        now = time.time()
        today = time.strftime("%Y-%m-%d", time.gmtime(now))
        try:
            with DB_LOCK:
                for day in days_to_close(ROOT, db, today):
                    res = IL.manifest_run(ROOT, db, day, OTS_BIN, now)
                    log(f"manifest {day} {json.dumps(res, sort_keys=True)}")
                    if "conflict" in res.values():
                        break
                if OTS_BIN and now - last_upgrade > 6 * 3600:
                    for mid in IL.machines(db):
                        results = L.ots_upgrade(IL.ledger_dir(ROOT, mid), OTS_BIN)
                        for name, st in results.items():
                            if st == "stamped":
                                db.execute("INSERT OR IGNORE INTO ots (machine_id, manifest, stamped_at) "
                                           "VALUES (?, ?, ?)", (mid, name, now))
                        n = AL.record_upgrades(db, mid, results, now)
                        log(f"ots upgrade {mid}: {n} newly upgraded of {len(results)}")
                    last_upgrade = now
                alerts = AL.evaluate_alerts(db, now)
            keys = sorted(AL.alert_key(a) for a in alerts)
            if keys != last_alerts:
                log(f"alerts {json.dumps(keys)}")
                if WEBHOOK:
                    req = urllib.request.Request(WEBHOOK, data=json.dumps({"alerts": alerts}).encode(),
                                                 headers={"Content-Type": "application/json"}, method="POST")
                    urllib.request.urlopen(req, timeout=15).close()
                last_alerts = keys
        except Exception as e:  # noqa: BLE001 - the scheduler must survive; the next tick retries
            log(f"scheduler error {type(e).__name__}: {e}")
        stop.wait(300)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    db = I.open_db(ROOT / "index.sqlite")
    if not I.load_tokens(TOKENS_PATH):
        log(f"WARN no machine tokens in {TOKENS_PATH}: every POST will be refused")
    stop = threading.Event()
    threading.Thread(target=scheduler, args=(db, stop), daemon=True).start()
    srv = ThreadingHTTPServer((LISTEN, PORT), Handler)
    srv.db = db
    log(f"listening on :{PORT}, data {ROOT}, ots {'yes' if OTS_BIN else 'NO'}")
    try:
        srv.serve_forever()
    finally:
        stop.set()


if __name__ == "__main__":
    main()
