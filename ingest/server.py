#!/usr/bin/env python3
"""bloom-ledger ingest server (stdlib only). Runs in Docker or directly on a Mac.

  POST /v1/objects   body = one spool object; headers Authorization: Bearer <machine token>, X-Bloom-Kind,
                     X-Bloom-Sha256. 201 stored, 200 already had it, 400/401/413/422 refused.
  GET  /healthz      200 {"ok": true, "objects": n} | 503
  GET  /v1/summary 200 {generated_at, machines: [per-machine day ribbon, last 90 UTC days]}  (metadata only)
  GET  /            the static dashboard page (dashboard.html)
  GET  /v1/tally/monthly?month=YYYY-MM, /v1/tally/months   read-only monthly books tally (see README)
  GET  /v1/invoice/monthly?month=YYYY-MM, /v1/invoice/months   read-only monthly invoice for the resell-tracker
  GET  /v1/withdrawals   read-only list of Darkbloom withdrawal requests found in the balance snapshots
  GET  /v1/earnings/series   daily earnings with a running total and a month roll-up (the home page graph)
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
import bloom_api_spend as SPD
import bloom_accounting_writeoff as WO
import bloom_pairing as PA  # noqa: E402
import bloom_accounting_admin as AA  # noqa: E402
import bloom_accounting_entries as AE  # noqa: E402
import bloom_accounting_page as PG  # noqa: E402
import bloom_accounting_receipts as RC  # noqa: E402
import bloom_accounting_report as RP  # noqa: E402
import bloom_accounting_summary as AS  # noqa: E402
import bloom_accounting_tax as AT  # noqa: E402
import bloom_accounting_tally as TL  # noqa: E402
import bloom_invoice as INV  # noqa: E402
import bloom_withdrawals as WD  # noqa: E402
import bloom_earnings_series as ES  # noqa: E402
import bloom_accounting_settings_form as SF  # noqa: E402
import bloom_accounting_deprpage as DPG  # noqa: E402
import bloom_accounting_config as ACF  # noqa: E402
import urllib.parse  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402
import bloom_lan as LAN  # noqa: E402
import bloom_migrate as MIG  # noqa: E402
import bloom_auth as AU  # noqa: E402
import bloom_web as WEB  # noqa: E402
import bloom_status as ST  # noqa: E402
import bloom_integrations as IG  # noqa: E402
import decimal  # noqa: E402
import bloom_doctor as DOC  # noqa: E402
import bloom_alerts as AL  # noqa: E402
import bloom_daily_push as DP  # noqa: E402
import bloom_ingest as I  # noqa: E402
import bloom_ingest_ledger as IL  # noqa: E402
import bloom_ledger as L  # noqa: E402
import bloom_settings as BS  # noqa: E402
import bloom_summary as SM  # noqa: E402

ROOT = Path(os.environ.get("BLOOM_DATA", "/data"))
TOKENS_PATH = os.environ.get("BLOOM_TOKENS", "/run/secrets/bloom_tokens")
LAN_URL = os.environ.get("BLOOM_LEDGER_LAN_URL", "")
PORT = int(os.environ.get("BLOOM_PORT", "8787"))
LISTEN = os.environ.get("BLOOM_LISTEN", "0.0.0.0")
WEBHOOK = os.environ.get("ALERT_WEBHOOK_URL", "")
PUSHOVER_TOKEN = os.environ.get("PUSHOVER_TOKEN", "")
PUSHOVER_USER = os.environ.get("PUSHOVER_USER", "")
# An hour of the UTC day (0-23), not local time: the push reports the previous UTC day.
DAILY_PUSH_HOUR = int(os.environ.get("DAILY_PUSH_HOUR", "9") or 9)
DASHBOARD = Path(__file__).resolve().parent / "dashboard.html"
MACHINES_PATH = os.environ.get("BLOOM_MACHINES", str(ROOT / "machines.json"))
SETTINGS = Path(__file__).resolve().parent / "settings.html"
EXPORT_PATHS = ("/v1/tally/monthly", "/v1/tally/months", "/v1/invoice/monthly", "/v1/invoice/months", "/v1/withdrawals")
DB_LOCK = threading.Lock()


def log(msg):
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}", flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "bloom-ledger/1"

    def log_message(self, fmt, *args):  # keep the access log free of headers; status + path only
        log(f"{self.address_string()} {fmt % args}")

    def handle_one_request(self):
        # A client that hangs up before the reply is written (a probe with a short timeout) is not a server
        # error. The access line is already logged; stop quietly instead of printing a traceback each time.
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def reply(self, code, obj, headers=None):
        data = json.dumps(obj, sort_keys=True).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def write_denied(self):
        """None when this request may write; else (status, body). Login when an admin exists (see bloom_auth)."""
        with DB_LOCK:
            return AU.write_denied(self.server.db, self.client_address[0], self.headers,
                                   lambda: LAN.write_guard(self.client_address[0], self.headers))

    def send_html(self, html, code=200):
        data = WEB.themed(html if isinstance(html, str) else html.decode("utf-8")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def get_new(self):
        """Routes added for first-run setup, login, status and static files. True when handled."""
        path = self.path.split("?", 1)[0]
        if path.startswith("/static/"):
            f = WEB.static_file(path[len("/static/"):])
            if f is None:
                self.reply(404, {"error": "not found"})
            else:
                self.send_response(200)
                self.send_header("Content-Type", f[0])
                self.send_header("Content-Length", str(len(f[1])))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(f[1])
            return True
        if path == "/login":
            self.send_html(WEB.login_page())
            return True
        if path == "/setup":
            with DB_LOCK:
                mode = AU.auth_mode(self.server.db)
                keep = mode == "lan" or AU.has_settings(self.server.db)
            needs = AU.setup_code_needed(LAN.is_private_ip(self.client_address[0]) and LAN.forwarded_ok(self.headers))
            self.send_html(WEB.setup_page(needs_code=needs and mode in ("setup", "lan"), keep_settings=keep))
            return True
        if path == "/status":
            self.send_html(WEB.status_page())
            return True
        if path == "/v1/auth/me":
            with DB_LOCK:
                mode = AU.auth_mode(self.server.db)
                ok = AU.session_ok(self.server.db, self.headers.get("Cookie"))
            self.reply(200, {"mode": mode, "logged_in": ok})
            return True
        if path == "/v1/status":
            now = time.time()
            with DB_LOCK:
                AX.create_schema(self.server.db)
                ids = sorted(set(I.load_tokens(TOKENS_PATH, MACHINES_PATH).values()))
                tz = ACF.ACCOUNTING_TZ
                data = ST.build(self.server.db, ROOT, now, ids, self.server_version, AU.auth_mode(self.server.db), tz,
                                MIG.export_api_enabled(self.server.db))
            self.reply(200, data)
            return True
        if path == "/v1/whoami":
            auth = self.headers.get("Authorization", "")
            tokens = I.load_tokens(TOKENS_PATH, MACHINES_PATH)
            import hashlib
            mid = tokens.get(hashlib.sha256(auth[7:].strip().encode()).hexdigest()) if auth.startswith("Bearer ") else None
            if mid:
                self.reply(200, {"machine_id": mid, "ok": True})
            else:
                self.reply(401, {"error": "unknown token", "ok": False})
            return True
        return False

    def post_new(self):
        """POST /v1/auth/*. True when handled."""
        if not self.path.startswith("/v1/auth/"):
            return False
        try:
            n = int(self.headers.get("Content-Length") or "-1")
        except ValueError:
            n = -1
        if n < 0 or n > 4096:
            self.reply(411 if n < 0 else 413, {"error": "bad length"})
            self.close_connection = True
            return True
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            self.reply(400, {"error": "bad request"})
            return True
        if not LAN.same_origin(self.headers):
            self.reply(403, {"error": "cross-origin request blocked"})
            return True
        ip = self.client_address[0]
        db = self.server.db
        if self.path == "/v1/auth/login":
            with DB_LOCK:
                if AU.locked(ip):
                    self.reply(429, {"error": "Too many wrong passwords. Wait a minute, then try again."})
                elif AU.has_admin(db) and AU.check_login(db, ip, body.get("username"), body.get("password")):
                    tok = AU.new_session(db)
                    self.reply(200, {"ok": True}, {"Set-Cookie": AU.cookie_header(tok, self.secure())})
                else:
                    self.reply(401, {"error": "Wrong username or password."})
        elif self.path == "/v1/auth/logout":
            with DB_LOCK:
                AU.end_session(db, self.headers.get("Cookie"))
            self.reply(200, {"ok": True}, {"Set-Cookie": AU.cookie_header("", self.secure(), clear=True)})
        elif self.path == "/v1/auth/setup":
            self.reply(*self.do_setup(body))
        else:
            self.reply(404, {"error": "not found"})
        return True

    def do_setup(self, body):
        db = self.server.db
        with DB_LOCK:
            if AU.has_admin(db):
                return (409, {"error": "Setup is already done. Log in instead."})
            local = LAN.is_private_ip(self.client_address[0]) and LAN.forwarded_ok(self.headers)
            if AU.setup_code_needed(local):
                if AU.locked(self.client_address[0]):
                    return (429, {"error": "Too many wrong codes or passwords. Wait a minute, then try again."})
                if not AU.setup_code_ok(ROOT, body.get("setup_code")):
                    AU.note_fail(self.client_address[0])
                    return (403, {"error": "That setup code is not right. It is printed in the server log."})
            # An install that already has history (migrated, or any time zone / price on record) keeps it: a change made here
            # applies from today, and only rewrites the past when the user ticks "apply to past days too".
            keep = AU.auth_mode(db) == "lan" or AU.has_settings(db)
            retro = bool(body.get("retroactive")) and keep
            since = "1970-01-01" if (retro or not keep) else ACF.utc_today()
            tz = str(body.get("timezone") or ("" if keep else "UTC")).strip() or None
            if tz is not None:
                try:
                    ZoneInfo(tz)
                except Exception:
                    return (400, {"error": "Unknown time zone. Use a name like America/Chicago or UTC."})
                if keep and tz == ACF.effective_settings(db, "9999-12-31")["values"]["local_timezone"]:
                    tz = None
            rate = None
            raw = str(body.get("rate") or "").strip().lstrip("$")
            if raw:
                try:
                    rate = decimal.Decimal(raw)
                    if not (0 <= rate <= 10):
                        raise ValueError
                except (decimal.InvalidOperation, ValueError):
                    return (400, {"error": "The electricity price should be a number like 0.15 (dollars per kWh)."})
            try:
                AU.create_admin(db, body.get("username"), body.get("password"))
            except ValueError as e:
                return (400, {"error": str(e)})
            now = int(time.time())
            if tz is not None:
                ACF.set_setting(db, "local_timezone", tz, since, now)
            if rate is not None:
                sched = [{"months": list(range(1, 13)), "periods": [{"start": "00:00", "end": "24:00", "rate": str(rate)}]}]
                ACF.set_setting(db, "rate_schedule", sched, since, now)
                if not keep:
                    for k in ("rate_adder_usd_per_kwh", "universal_charge_usd_per_kwh", "county_fee_pct"):
                        ACF.set_setting(db, k, 0, since, now)
            if body.get("bloomgauge"):
                IG.set_bloomgauge(db, True)
            tok = AU.new_session(db)
        AU.rotate_setup_code(ROOT)
        AU.clear_fails(self.client_address[0])
        log("setup finished: admin created")
        return (200, {"ok": True}, {"Set-Cookie": AU.cookie_header(tok, self.secure())})

    def secure(self):
        return self.headers.get("X-Forwarded-Proto", "").lower() == "https"

    def send_bytes(self, ctype, data):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?", 1)[0] in EXPORT_PATHS:
            with DB_LOCK:
                on = MIG.export_api_enabled(self.server.db)
            if not on:
                self.reply(404, {"error": "not found"})
                return
        if self.get_new():
            return
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
                today = (q.get("today") or [ACF.utc_today()])[0]
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
                self.reply(200, RP.day_detail(self.server.db, ACF.ACCOUNTING_TZ, date, machine, settings))
        elif self.path == "/v1/summary":
            with DB_LOCK:
                self.reply(200, SM.summary(self.server.db, ROOT, time.time()))
        elif self.path.split("?", 1)[0] in ("/tax", "/tax/packet", "/v1/accounting/tax"):
            with DB_LOCK:
                AX.create_schema(self.server.db)
                code, ctype, data = AT.tax_response(self.server.db, self.path)
            if ctype.startswith("text/html"):
                data = WEB.themed(data.decode("utf-8")).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path.split("?", 1)[0] in ("/v1/tally/monthly", "/v1/tally/months"):
            with DB_LOCK:
                AX.create_schema(self.server.db)
                code, ctype, data = TL.tally_response(self.server.db, self.path, time.time())
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        elif self.path.split("?", 1)[0] in ("/v1/invoice/monthly", "/v1/invoice/months"):
            with DB_LOCK:
                AX.create_schema(self.server.db)
                code, ctype, data = INV.invoice_response(self.server.db, self.path, time.time())
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        elif self.path.split("?", 1)[0] == "/v1/withdrawals":
            with DB_LOCK:
                AX.create_schema(self.server.db)
                code, ctype, data = WD.withdrawals_response(self.server.db, self.path, time.time())
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        elif self.path.split("?", 1)[0] == "/v1/earnings/series":
            with DB_LOCK:
                AX.create_schema(self.server.db)
                code, ctype, data = ES.series_response(self.server.db, self.path)
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        elif self.path in ("/", "/index.html", "/log"):
            self.send_html(DASHBOARD.read_bytes() if self.path == "/log" else PG.render_page())
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
            self.send_html(SF.settings_form_page())
        elif self.path == "/settings/depreciation":
            self.send_html(DPG.page())
        elif self.path == "/v1/accounting/depreciation":
            import bloom_machine_profiles as MP
            with DB_LOCK:
                self.reply(200, DPG.depreciation_data(self.server.db, MP.list_profiles(self.server.db)))
        elif self.path == "/v1/hello":
            self.reply(200, {"service": "bloom-ledger", "server_id": PA.server_id(ROOT), "client_version": PA.client_version()})
        elif self.path == "/install.sh":
            script = PA.install_script(self.headers.get("Host"), lan_url=LAN_URL)
            if script is None:
                self.reply(400, {"error": "bad Host header"})
            else:
                self.send_bytes("text/x-shellscript; charset=utf-8", script.encode())
        elif self.path == "/client.tar.gz":
            self.send_bytes("application/gzip", PA.client_bundle())
        elif self.path == "/settings":
            self.send_html(SETTINGS.read_bytes())
        elif self.path == "/v1/settings":
            with DB_LOCK:
                now = time.time()
                ids = sorted(set(I.load_tokens(TOKENS_PATH, MACHINES_PATH).values()))
                data = {
                    "machines": BS.machine_rows(self.server.db, ROOT, now, ids),
                    "health": BS.ledger_health(self.server.db, ROOT, now, self.server_version),
                    "darkbloom_key": LV.key_status(ROOT),
                    "lan_url": PA.ledger_base(self.headers.get("Host"), LAN_URL),
                    "write_off": WO.rules(ACF.effective_settings(self.server.db, ACF.utc_today())["values"]),
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
        if self.post_new():
            return
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
            denied = self.write_denied()
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
                    code, obj = BS.admin_post(self.path, self.headers, body, MACHINES_PATH, time.time(),
                                              set(I.load_tokens(TOKENS_PATH).values()))
            self.reply(code, PA.after_machine_change(self.path, code, obj, body, dbkey, ROOT, time.time()))
        elif self.path.startswith("/v1/accounting/"):
            denied = self.write_denied()
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
            if n > (RC.MAX_BYTES if rid else 65536 if self.path == "/v1/accounting/settings" else 4096):  # machine lists pass 4 KB
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


def daily_push_tick(db):
    """Send yesterday's push if due. DAILY_PUSH_HOUR is an hour of the UTC day, and "yesterday" is the UTC day before."""
    with DB_LOCK:
        return DP.run(ROOT / "daily-push.json", ACF.utc_now(), DAILY_PUSH_HOUR,
                      lambda day, period: AS.build(db, day, period), PUSHOVER_TOKEN, PUSHOVER_USER)


def scheduler(db, stop):
    last_alerts = None
    last_spend = 0.0
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
            if now - last_spend >= SPD.EVERY_S:
                last_spend = now
                res = SPD.ingest(db, ROOT, now, DB_LOCK)   # the HTTP call runs outside the lock; never logs the key
                if res["added"] or res["state"] not in ("ok", "no_key", "no_start"):
                    log(f"api spend {json.dumps(res, sort_keys=True)}")
            keys = sorted(AL.alert_key(a) for a in alerts)
            if keys != last_alerts:
                log(f"alerts {json.dumps(keys)}")
                if WEBHOOK:
                    req = urllib.request.Request(WEBHOOK, data=json.dumps({"alerts": alerts}).encode(),
                                                 headers={"Content-Type": "application/json"}, method="POST")
                    urllib.request.urlopen(req, timeout=15).close()
                last_alerts = keys
            sent = daily_push_tick(db)
            if sent:
                log(f"daily push sent for {sent}")
        except Exception as e:  # noqa: BLE001 - the scheduler must survive; the next tick retries
            log(f"scheduler error {type(e).__name__}: {e}")
        stop.wait(300)


def reset_admin():
    """`server.py reset-admin`: remove the admin account and its sessions so /setup can create a new one."""
    db = I.open_db(ROOT / "index.sqlite")
    AU.create_tables(db)
    db.execute("DELETE FROM bl_admin")
    db.execute("DELETE FROM bl_sessions")
    db.commit()
    print("Admin removed. Open /setup in the browser to create a new one. Setup code: %s" % AU.setup_code(ROOT))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        sys.exit(DOC.run(ROOT, TOKENS_PATH, MACHINES_PATH, PORT, time.time()))
    if len(sys.argv) > 1 and sys.argv[1] == "reset-admin":
        return reset_admin()
    if len(sys.argv) > 1:
        print("usage: server.py [doctor | reset-admin]   (no argument starts the server)")
        sys.exit(2)
    ROOT.mkdir(parents=True, exist_ok=True)
    why = MIG.legacy_bind_data(ROOT, os.environ.get("BLOOM_LEGACY_DIR", ""))
    if why:
        log(why)
        sys.exit(3)
    db = I.open_db(ROOT / "index.sqlite")
    MIG.run(db, log)
    mode = AU.auth_mode(db)
    if mode == "setup":
        log(f"first run: open http://<this machine>:{PORT}/setup to create the admin login. Setup code: {AU.setup_code(ROOT)}")
    elif mode == "lan":
        log(f"no admin login yet: settings are open to the local network only. Open http://<this machine>:{PORT}/setup to create one. Setup code: {AU.setup_code(ROOT)}")
    if not I.load_tokens(TOKENS_PATH, MACHINES_PATH):
        log("no Macs added yet: add one at /setup or Settings. Data posts are refused until then.")
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
