"""`server.py doctor`: check every prerequisite of the server and print pass/fail with the fix. Read-only; exit 1 on any FAIL."""
import json
import os
import shutil
import sqlite3
import sys
import urllib.request
from pathlib import Path

import bloom_accounting_config as ACF
import bloom_auth as AU
import bloom_ingest as I
import bloom_integrations as IG
import bloom_migrate as MIG


def checks(root, tokens_path, machines_path, port, now):
    """[(status, name, detail, fix)] with status PASS, WARN, FAIL or INFO. Never raises."""
    out = []

    def add(status, name, detail="", fix=""):
        out.append((status, name, detail, fix))

    add("PASS" if sys.version_info >= (3, 9) else "FAIL", "Python 3.9 or newer", sys.version.split()[0],
        "Install Python 3.9+ (Mac: brew install python). The Docker image already has it.")
    root = Path(root)
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".doctor-write-test"
        probe.write_text("x")
        probe.unlink()
        add("PASS", "Data folder is writable", str(root))
    except OSError as e:
        add("FAIL", "Data folder is writable", "%s: %s" % (root, type(e).__name__),
            "Make the folder writable by the user running the server (Docker: check the volume owner; Mac: chown it to your user).")
    try:
        free = shutil.disk_usage(str(root)).free
        add("PASS" if free > 1 << 30 else "WARN", "Free disk space", "%.1f GB" % (free / 1e9), "Free some space; the ledger stores every file it receives.")
    except OSError:
        add("WARN", "Free disk space", "unknown")
    db = None
    try:
        db = sqlite3.connect(str(root / "index.sqlite"), timeout=10)
        res = db.execute("PRAGMA integrity_check").fetchone()[0]
        add("PASS" if res == "ok" else "FAIL", "Database is healthy", res,
            "Restore index.sqlite from a backup, or delete it and restart: it is rebuilt from the stored files.")
    except sqlite3.Error as e:
        add("FAIL", "Database opens", type(e).__name__, "Check the data folder permissions and that the file is not locked by another server.")
    if db is not None:
        try:
            mode = AU.auth_mode(db)
            add("PASS" if mode in ("login", "off") else "WARN", "Admin login", {"login": "admin created", "off": "BLOOM_AUTH=off", "lan": "no admin yet (local network only)", "setup": "not created yet"}[mode],
                "Open http://<this server>:%s/setup and create the admin account." % port)
            tz = ACF.effective_settings(db, "9999-12-31")["values"]
            add("PASS" if tz["local_timezone"] else "FAIL", "Time zone", tz["local_timezone"], "Set it in /setup or Accounting settings.")
            add("PASS" if tz.get("rate_schedule") else "INFO", "Electricity price", "set" if tz.get("rate_schedule") else "not set (power cost is not computed)",
                "Optional: enter it under Accounting settings.")
            add("INFO", "Export API (resell tracker)", "on" if MIG.export_api_enabled(db) else "off", "Set BLOOM_ENABLE_EXPORT_API=1 to turn it on.")
        except Exception as e:
            add("FAIL", "Settings readable", type(e).__name__, "The database may be damaged; see the previous check.")
        finally:
            db.close()
    ids = set(I.load_tokens(tokens_path, machines_path).values())
    add("PASS" if ids else "WARN", "Macs added", "%d" % len(ids), "Add one at /setup or Machines, then run the shown command on the Mac.")
    try:
        with urllib.request.urlopen("http://127.0.0.1:%s/healthz" % port, timeout=3) as r:
            add("PASS" if r.status == 200 else "FAIL", "Server answers on port %s" % port, "healthz %s" % r.status, "Look at the server log for the error.")
    except Exception:
        add("WARN", "Server answers on port %s" % port, "not reachable from here", "Start it (docker compose up -d, or the launchd service), then rerun doctor.")
    g = IG.bloomgauge_state()
    add("INFO", "BloomGauge (optional)", "switched on" if g == "enabled" else "optional: not set up", "Nothing to do. It is never required.")
    return out


def run(root, tokens_path, machines_path, port, now):
    rows = checks(root, tokens_path, machines_path, port, now)
    for status, name, detail, fix in rows:
        print("[%-4s] %s%s" % (status, name, (": " + detail) if detail else ""))
        if status in ("FAIL", "WARN") and fix:
            print("       fix: " + fix)
    bad = [r for r in rows if r[0] == "FAIL"]
    print("\n%s" % ("All required checks passed." if not bad else "%d check%s failed." % (len(bad), "" if len(bad) == 1 else "s")))
    return 1 if bad else 0
