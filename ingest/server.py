#!/usr/bin/env python3
"""bloom-ledger ingest server (stdlib only). Runs in the Unraid container.

  POST /v1/objects   body = one spool object; headers Authorization: Bearer <machine token>, X-Bloom-Kind,
                     X-Bloom-Sha256. 201 stored, 200 already had it, 400/401/413/422 refused.
  GET  /healthz      200 {"ok": true, "objects": n} | 503
  GET  /v1/summary 200 {generated_at, machines: [per-machine day ribbon, last 90 UTC days]}  (metadata only)
  GET  /            the static dashboard page (dashboard.html)
  GET  /v1/alerts    200 [open alerts]  (machine silent > 30 min, ring snapshot > 12 h)

Background: every 10 min closes every finished UTC day since the last manifest (per machine, hash-chained);
every 5 min evaluates alerts and, when the open set
changes, POSTs it to ALERT_WEBHOOK_URL (optional). Env: BLOOM_DATA (/data), BLOOM_TOKENS
(/run/secrets/bloom_tokens), BLOOM_PORT (8787), ALERT_WEBHOOK_URL.
Logs carry machine ids, counts and statuses only; never a token or a request body."""
import datetime as dt
import json
import os
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bloom_accounting_index as AX  # noqa: E402
import bloom_accounting_live as LV
import bloom_accounting_writeoff as WO
import bloom_pairing as PA  # noqa: E402
import bloom_accounting_admin as AA  # noqa: E402
import bloom_accounting_entries as AE  # noqa: E402
import bloom_accounting_page as PG  # noqa: E402
import bloom_accounting_receipts as RC  # noqa: E402
import bloom_accounting_report as RP  # noqa: E402
import bloom_accounting_summary as AS  # noqa: E402
import bloom_accounting_tax as AT  # noqa: E402
import bloom_accounting_settings_form as SF  # noqa: E402
import bloom_accounting_config as ACF  # noqa: E402
import urllib.parse  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402
import bloom_lan as LAN  # noqa: E402
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
WEBHOOK = os.environ.get("ALERT_WEBHOOK_URL", "")
DASHBOARD = Path(__file__).resolve().parent / "dashboard.html"
MACHINES_PATH = os.environ.get("BLOOM_MACHINES", str(ROOT / "machines.json"))
SETTINGS = Path(__file__).resolve().parent / "settings.html"
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

    def send_bytes(self, ctype, data):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            with DB_LOCK:
                self.reply(*I.healthz(ROOT, self.server.db))
        elif self.path == "/v1/accounting/entries":
            with DB_LOCK:
                self.reply(200, {"entries": AE.current_entries(self.server.db)})
        elif self.path.split("?", 1)[0] == "/v1/accounting/summary":
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            period = (q.get("period") or ["month"])[0]
            machine = (q.get("machine") or [None])[0] or None
            with DB_LOCK:
                tz = ACF.effective_settings(self.server.db, "9999-12-31")["values"]["local_timezone"]
                today = (q.get("today") or [dt.datetime.now(ZoneInfo(tz)).date().isoformat()])[0]
                AX.create_schema(self.server.db)
                try:
                    self.reply(200, AS.build(self.server.db, today, period, machine))
                except ValueError:
                    self.reply(400, {"error": "bad period or date"})
        elif self.path.split("?", 1)[0] == "/v1/accounting/day":
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            date = (q.get("date") or [""])[0]
            machine = (q.get("machine") or [None])[0] or None
            try:
                dt.date.fromisoformat(date)
            except ValueError:
                self.reply(400, {"error": "date must be YYYY-MM-DD"})
                return
            with DB_LOCK:
                AX.create_schema(self.server.db)
                settings = ACF.effective_settings(self.server.db, date)["values"]
                self.reply(200, RP.day_detail(self.server.db, settings["local_timezone"], date, machine, settings))
        elif self.path == "/v1/summary":
            with DB_LOCK:
                self.reply(200, SM.summary(self.server.db, ROOT, time.time()))
        elif self.path.split("?", 1)[0] in ("/tax", "/tax/packet", "/v1/accounting/tax"):
            with DB_LOCK:
                AX.create_schema(self.server.db)
                code, ctype, data = AT.tax_response(self.server.db, self.path)
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path in ("/", "/index.html", "/log"):
            data = DASHBOARD.read_bytes() if self.path == "/log" else PG.render_page().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/v1/alerts":
            with DB_LOCK:
                self.reply(200, AL.evaluate_alerts(self.server.db, time.time()))
        elif self.path == "/v1/live":
            now = time.time()
            with DB_LOCK:
                AX.create_schema(self.server.db)
                mac = LV.mac_view(self.server.db, now)
            self.reply(200, LV.live(ROOT, mac, now))
        elif self.path == "/v1/settings/darkbloom-key":
            self.reply(200, LV.key_status(ROOT))
        elif self.path == "/settings/accounting":
            data = SF.settings_form_page().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/v1/hello":
            self.reply(200, {"service": "bloom-ledger", "server_id": PA.server_id(ROOT), "client_version": PA.client_version()})
        elif self.path == "/install.sh":
            script = PA.install_script(self.headers.get("Host"))
            if script is None:
                self.reply(400, {"error": "bad Host header"})
            else:
                self.send_bytes("text/x-shellscript; charset=utf-8", script.encode())
        elif self.path == "/client.tar.gz":
            self.send_bytes("application/gzip", PA.client_bundle())
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
                    "machines": BS.machine_rows(self.server.db, ROOT, now, ids),
                    "health": BS.ledger_health(self.server.db, ROOT, now, self.server_version),
                    "darkbloom_key": LV.key_status(ROOT),
                    "write_off": WO.rules(ACF.effective_settings(self.server.db, dt.date.today().isoformat())["values"]),
                }
                self.reply(200, data)
        elif RC.entry_id_from_path(self.path):
            with DB_LOCK:
                code, ctype, data = RC.receipt_get(self.server.db, ROOT, RC.entry_id_from_path(self.path))
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/v1/pair":
            # curl on the new Mac sends no Origin, so this is LAN-only without the same-origin rule; the code is the secret.
            if not LAN.is_private_ip(self.client_address[0]) or not LAN.forwarded_ok(self.headers):
                self.reply(403, {"error": "local network only"})
                return
            try:
                n = int(self.headers.get("Content-Length") or "-1")
            except ValueError:
                n = -1
            if n < 0 or n > 1024:
                self.reply(413 if n > 1024 else 411, {"error": "bad length"})
                self.close_connection = True
                return
            self.reply(*PA.redeem(self.rfile.read(n), time.time(), PA.server_id(ROOT)))
            return
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
            denied = LAN.write_guard(self.client_address[0], self.headers)
            if denied:
                self.reply(*denied)
                return
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
            if self.path == "/v1/settings/darkbloom-key":
                self.reply(*LV.key_post(ROOT, body, time.time()))
                return
            import bloom_machine_profiles as MP
            dbkey = PA.requested_key(self.path, body)
            if dbkey is not None and not LV.valid_key(dbkey):
                self.reply(400, {"error": "that doesn't look like a Darkbloom API key"})
                return
            with DB_LOCK:
                if self.path in ("/v1/settings/machines/profile", "/v1/settings/machines/remove"):
                    code, obj = MP.profile_post(self.path, body, self.server.db, MACHINES_PATH, time.time())
                else:
                    code, obj = BS.admin_post(self.path, self.headers, body, MACHINES_PATH, time.time())
            self.reply(code, PA.after_machine_change(self.path, code, obj, body, dbkey, ROOT, time.time()))
        elif self.path.startswith("/v1/accounting/"):
            denied = LAN.write_guard(self.client_address[0], self.headers)
            if denied:
                self.reply(*denied)
                return
            try:
                n = int(self.headers.get("Content-Length") or "-1")
            except ValueError:
                n = -1
            if n < 0:
                self.reply(411, {"error": "length required"})
                return
            rid = RC.entry_id_from_path(self.path)
            if n > (RC.MAX_BYTES if rid else 4096):
                self.reply(413, {"error": "too large"})
                self.close_connection = True
                return
            body = self.rfile.read(n)
            with DB_LOCK:
                if rid:
                    code, obj = RC.receipt_post(self.server.db, ROOT, rid, self.headers.get("Content-Type"), body)
                else:
                    code, obj = AA.accounting_post(self.path, self.headers, body, self.server.db, time.time())
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
    last_alerts = None
    while not stop.wait(1):
        now = time.time()
        today = time.strftime("%Y-%m-%d", time.gmtime(now))
        try:
            with DB_LOCK:
                for day in days_to_close(ROOT, db, today):
                    res = IL.manifest_run(ROOT, db, day)
                    log(f"manifest {day} {json.dumps(res, sort_keys=True)}")
                    if "conflict" in res.values():
                        break
                AX.create_schema(db)
                n = AX.index_new(db, ROOT)
                if n:
                    log(f"accounting indexed {n} objects")
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
    log(f"listening on :{PORT}, data {ROOT}")
    try:
        srv.serve_forever()
    finally:
        stop.set()


if __name__ == "__main__":
    main()
