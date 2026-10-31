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
    db.execute(
        "CREATE TABLE IF NOT EXISTS acct_settings ("
        "key TEXT NOT NULL, effective_from TEXT NOT NULL, "
        "value_json TEXT NOT NULL, created_at INTEGER NOT NULL)"
    )
    db.commit()


def set_setting(db, key, value, effective_from, now):
    if key not in DEFAULTS:
        raise ValueError(f"unknown key: {key!r}")
    if not isinstance(effective_from, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", effective_from):
        raise ValueError(f"bad effective_from: {effective_from!r}")
    create_settings_table(db)
    db.execute(
        "INSERT INTO acct_settings (key, effective_from, value_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        (key, effective_from, json.dumps(value), int(now)),
    )
    db.commit()
