"""Machine profiles for the ledger Settings page: display name, model and lease fields per machine id (stdlib only).

Stored in the ledger's sqlite index db. A profile is never deleted; removing a machine only sets active to 0, so
every historical row for that machine stays. Money is integer cents, dates are YYYY-MM-DD."""
import datetime as dt

import bloom_ingest

FIELDS = ("display_name", "model", "lease_start", "lease_monthly_cents")


def create_table(db):
    db.execute("CREATE TABLE IF NOT EXISTS machine_profiles (machine_id TEXT PRIMARY KEY, display_name TEXT, model TEXT,"
               " lease_start TEXT, lease_monthly_cents INTEGER, active INTEGER NOT NULL DEFAULT 1,"
               " updated_at INTEGER NOT NULL)")
    db.commit()


def validate_profile(fields):
    errors = {}
    if not isinstance(fields, dict):
        return {"form": "not an object"}
    for key in fields:
        if key not in FIELDS:
            errors[str(key)] = "unknown field"
            continue
        val = fields[key]
        if val is None:
            continue
        if key == "display_name" or key == "model":
            if not isinstance(val, str):
                errors[key] = "must be a string"
            elif not val.strip():
                errors[key] = "must not be blank"
            elif len(val) > 60:
                errors[key] = "too long"
        elif key == "lease_start":
            if not isinstance(val, str) or len(val) != 10:
                errors[key] = "invalid date string"
            else:
                try:
                    dt.date.fromisoformat(val)
                except ValueError:
                    errors[key] = "invalid date"
        elif key == "lease_monthly_cents":
            if isinstance(val, bool) or not isinstance(val, int) or val <= 0:
                errors[key] = "must be a positive integer"
    return errors



def list_profiles(db):
    create_table(db)
    out = {}
    for mid, name, model, start, cents, active in db.execute(
            "SELECT machine_id, display_name, model, lease_start, lease_monthly_cents, active FROM machine_profiles"):
        out[mid] = {"display_name": name, "model": model, "lease_start": start, "lease_monthly_cents": cents,
                    "active": bool(active)}
    return out
