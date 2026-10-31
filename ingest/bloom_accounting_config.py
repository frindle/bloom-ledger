"""Accounting settings for the bloom-ledger ingest (stdlib only). Settings are append-only, effective-dated rows; a key never
set falls back to DEFAULTS, and every default that is an assumption is listed in FLAGGED so reports can show it.
Bookkeeping estimates, not tax advice."""
import json
import re

DEFAULTS = {
    "ingest_from": "2026-10-13",
    "m4_in_service_date": "2026-10-01",
    "nevada_fee_pct": None,
    "kwh_rate_cents": None,
    "m5_lease_start": None,
    "dep_method": "straight_line",
    "dep_life_months": 60,
}
FLAGGED = {
    "m4_in_service_date": "ASSUMED 2026-10-01 (Darkbloom start); confirm the real placed-in-service date",
    "nevada_fee_pct": "UNKNOWN: not applied until set; confirm whether earnings rows are already net of the fee",
    "kwh_rate_cents": "UNKNOWN: power cost is not computed until the electricity rate is set",
    "m5_lease_start": "UNKNOWN: no lease expense until the M5 start date is set at delivery",
    "dep_method": "DEFAULT straight_line over dep_life_months; the accountant picks the method",
}


def create_settings_table(db):
    """Create acct_settings(key, effective_from, value_json, created_at) if missing."""
    db.execute("CREATE TABLE IF NOT EXISTS acct_settings (key TEXT NOT NULL, effective_from TEXT NOT NULL,"
               " value_json TEXT NOT NULL, created_at INTEGER NOT NULL)")
    db.commit()


def set_setting(db, key, value, effective_from, now):
    """Append a settings row; ValueError for an unknown key or a malformed YYYY-MM-DD date. Rows are never edited."""
    if key not in DEFAULTS:
        raise ValueError("unknown setting " + str(key))
    if not isinstance(effective_from, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", effective_from):
        raise ValueError("effective_from must be YYYY-MM-DD")
    create_settings_table(db)
    db.execute("INSERT INTO acct_settings (key, effective_from, value_json, created_at) VALUES (?, ?, ?, ?)",
               (key, effective_from, json.dumps(value), int(now)))
    db.commit()


def effective_settings(db, on_date):
    create_settings_table(db)
    rows = db.execute(
        "SELECT key, effective_from, value_json, created_at, rowid "
        "FROM acct_settings WHERE effective_from <= ? ORDER BY effective_from, created_at, rowid",
        (on_date,)
    ).fetchall()
    values = dict(DEFAULTS)
    best = {}
    for key, effective_from, value_json, created_at, rowid in rows:
        parsed = json.loads(value_json)
        if key not in best or (effective_from, created_at, rowid) > (best[key][0], best[key][1], best[key][2]):
            best[key] = (effective_from, created_at, rowid, parsed)
    for key in best:
        values[key] = best[key][3]
    flags = []
    for k in FLAGGED:
        if k not in best or best[k][3] is None:
            flags.append({"key": k, "reason": FLAGGED[k]})
    return {"values": values, "flags": flags}
