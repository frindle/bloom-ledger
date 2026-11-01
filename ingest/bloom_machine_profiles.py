"""Machine profiles for the ledger Settings page: display name, model and lease fields per machine id (stdlib only).

Stored in the ledger's sqlite index db. A profile is never deleted; removing a machine only sets active to 0, so
every historical row for that machine stays. Money is integer cents, dates are YYYY-MM-DD."""
import datetime as dt

import bloom_ingest

FIELDS = ("display_name", "model", "lease_start", "lease_monthly_cents")


def create_table(db):
    db.execute("CREATE TABLE IF NOT EXISTS machine_profiles (machine_id TEXT PRIMARY KEY, display_name TEXT, model TEXT, lease_start TEXT, lease_monthly_cents INTEGER, active INTEGER NOT NULL DEFAULT 1, updated_at INTEGER NOT NULL)")
    db.commit()


def list_profiles(db):
    create_table(db)
    rows = db.execute("SELECT machine_id, display_name, model, lease_start, lease_monthly_cents, active FROM machine_profiles").fetchall()
    return {(mid): {"display_name": display_name, "model": model, "lease_start": lease_start, "lease_monthly_cents": lease_monthly_cents, "active": bool(active)} for mid, display_name, model, lease_start, lease_monthly_cents, active in rows}
