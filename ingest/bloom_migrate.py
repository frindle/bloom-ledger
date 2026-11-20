"""One-time upgrades of an existing database (stdlib only). Each step runs once, is recorded in acct_meta, and never
fails the server: an error is logged and skipped so a bad step cannot stop a start.

legacy_defaults_v1: older versions assumed America/Los_Angeles, an ingest start of 2026-10-13 and an in-service date of
2026-09-28 when nothing was set. Those assumptions are gone from the defaults. A database that already holds earnings
is pinned to the old values (as ordinary dated settings rows) so its numbers do not change. A fresh database is left
alone and the step is marked done, so a new install never inherits them."""
import time

import bloom_accounting_config as CF

LEGACY = {"local_timezone": "America/Los_Angeles", "ingest_from": "2026-10-13", "m4_in_service_date": "2026-09-28"}


def _table_has_rows(db, table):
    try:
        return db.execute("SELECT 1 FROM " + table + " LIMIT 1").fetchone() is not None
    except Exception:
        return False


def run(db, log=print):
    """Apply every pending step. Returns the list of step names applied this call."""
    db.execute("CREATE TABLE IF NOT EXISTS acct_meta (k TEXT PRIMARY KEY, v TEXT)")
    applied = []
    key = "migration_legacy_defaults_v1"
    if db.execute("SELECT 1 FROM acct_meta WHERE k = ?", (key,)).fetchone() is None:
        try:
            CF.create_settings_table(db)
            existing = _table_has_rows(db, "earnings") or _table_has_rows(db, "power_minutes") or _table_has_rows(db, "acct_entries")
            if existing:
                have = {r[0] for r in db.execute("SELECT DISTINCT key FROM acct_settings")}
                for k, v in LEGACY.items():
                    if k not in have:
                        CF.set_setting(db, k, v, "1970-01-01", int(time.time()))
                db.execute("INSERT OR IGNORE INTO acct_meta (k, v) VALUES ('export_api', '1')")  # old installs keep the export API
                applied.append(key)
                log("migrated existing database: kept the old timezone, start date and in-service date as settings")
            db.execute("INSERT OR REPLACE INTO acct_meta (k, v) VALUES (?, ?)", (key, "1" if existing else "fresh"))
            db.commit()
        except Exception as e:  # never block a start
            log("migration %s skipped: %s" % (key, type(e).__name__))
    return applied


def export_api_enabled(db, env=None):
    """The resell-tracker export API (/v1/tally, /v1/invoice, /v1/withdrawals) is off unless BLOOM_ENABLE_EXPORT_API is
    1/true/yes/on, or the database was migrated from an older install that already used it."""
    import os
    env = os.environ if env is None else env
    if str(env.get("BLOOM_ENABLE_EXPORT_API", "")).strip().lower() in ("1", "true", "yes", "on"):
        return True
    try:
        r = db.execute("SELECT v FROM acct_meta WHERE k = 'export_api'").fetchone()
        return bool(r and r[0] == "1")
    except Exception:
        return False


def _has_data(folder):
    try:
        return (folder / "index.sqlite").exists() or (folder / "objects").is_dir()
    except OSError:
        return False


def legacy_bind_data(root, legacy):
    """Compose installs from before named volumes kept their data in ./data next to compose.yaml, with no .env. Compose now
    mounts the project folder read-only at `legacy` (BLOOM_LEGACY_DIR). When that folder has a ./data with a ledger in it and
    the real data folder (`root`) is empty, starting would silently show an empty ledger: return the message to print instead
    (None when all is well or when the legacy folder is not readable)."""
    from pathlib import Path
    if not legacy:
        return None
    root, old = Path(root), Path(legacy) / "data"
    if _has_data(root) or not _has_data(old):
        return None
    return ("refusing to start: found data from an older install in ./data, but this container is using an empty data volume, "
            "so you would see an empty ledger. Keep your data: put these lines in a file named .env next to compose.yaml "
            "(or run ./update.sh, which writes them) and start again:\n"
            "  BLOOM_DATA_DIR=./data\n  BLOOM_KEYS_DIR=./data/secrets\n  BLOOM_SECRETS_DIR=./secrets\n  BLOOM_EARNINGS_DIR=./data/earnings\n"
            "Your data was not touched.")
