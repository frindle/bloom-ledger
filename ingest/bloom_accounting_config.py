"""Accounting settings for the bloom-ledger ingest (stdlib only). Settings are append-only, effective-dated rows; a key never
set falls back to DEFAULTS, and every default that is an assumption is listed in FLAGGED so reports can show it.
Bookkeeping estimates, not tax advice."""
import json
import re

DEFAULTS = {
    "ingest_from": "2026-10-13",
    "m4_in_service_date": "2026-09-28",
    "m5_lease_start": None,
    "m5_lease_monthly_cents": None,
    "m5_lease_months": None,
    "m5_business_mode": "leased_100",
    "m4_business_mode": "auto_paid_hours",
    "machine_ids": None,
    "m4_machine_id": None,
    "m5_machine_id": None,
    "rate_schedule": None,
    "rate_adder_usd_per_kwh": None,
    "universal_charge_usd_per_kwh": None,
    "county_fee_pct": None,
    "local_timezone": "America/Los_Angeles",
    "dep_method": "macrs5",
    "dep_life_months": 60,
    "machines": None,
    "entry_machine_links": None,
}
FLAGGED = {
    "m4_in_service_date": "ASSUMED 2026-09-28 (Darkbloom start); confirm the real placed-in-service date",
    "rate_schedule": "UNKNOWN: power cost is not computed until the electricity rate schedule is entered in Settings",
    "rate_adder_usd_per_kwh": "UNKNOWN: optional per-kWh adder; none applied until entered",
    "universal_charge_usd_per_kwh": "UNKNOWN: optional per-kWh universal energy charge; none applied until entered",
    "county_fee_pct": "UNKNOWN: optional county fee percent; none applied until entered",
    "m5_lease_monthly_cents": "UNKNOWN: no lease expense until the monthly lease amount is set",
    "m5_lease_start": "UNKNOWN: no lease expense until the M5 start date is set at delivery",
    "dep_method": "DEFAULT macrs5 (5-year MACRS, half-year convention); the accountant confirms the method",
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
    """{'values': {key: value}, 'flags': [{'key', 'reason'}]} as of the YYYY-MM-DD `on_date`; defaults fill the gaps."""
    create_settings_table(db)
    values = dict(DEFAULTS)
    set_keys = set()
    rows = db.execute("SELECT key, value_json FROM acct_settings WHERE effective_from <= ? ORDER BY effective_from, created_at, rowid",
                      (on_date,)).fetchall()
    for key, value_json in rows:
        values[key] = json.loads(value_json)
        set_keys.add(key)
    flags = [{"key": k, "reason": FLAGGED[k]} for k in FLAGGED if k not in set_keys or values[k] is None]
    return {"values": values, "flags": flags}
