"""Machine profiles for the ledger Settings page: display name, model and lease fields per machine id (stdlib only).

Stored in the ledger's sqlite index db. A profile is never deleted; removing a machine only sets active to 0, so
every historical row for that machine stays. Money is integer cents, dates are YYYY-MM-DD."""
import datetime as dt

import bloom_ingest

ACQUISITIONS = ("leased", "purchased")
FIELDS = ("display_name", "model", "lease_start", "lease_monthly_cents", "acquisition", "in_service", "purchase_cents")


def create_table(db):
    db.execute("CREATE TABLE IF NOT EXISTS machine_profiles (machine_id TEXT PRIMARY KEY, display_name TEXT, model TEXT,"
               " lease_start TEXT, lease_monthly_cents INTEGER, active INTEGER NOT NULL DEFAULT 1,"
               " updated_at INTEGER NOT NULL)")
    cols = [r[1] for r in db.execute("PRAGMA table_info(machine_profiles)")]
    if "acquisition" not in cols:
        db.execute("ALTER TABLE machine_profiles ADD COLUMN acquisition TEXT")
    for col, typ in (("in_service", "TEXT"), ("purchase_cents", "INTEGER")):
        if col not in cols:
            db.execute("ALTER TABLE machine_profiles ADD COLUMN " + col + " " + typ)
    db.commit()


def validate_profile(fields):
    if not isinstance(fields, dict):
        return {"form": "not an object"}
    errors = {}
    for key in fields:
        if key not in FIELDS:
            errors[str(key)] = "unknown field"
    for key in ("display_name", "model"):
        if key in fields:
            v = fields[key]
            if v is not None and not (isinstance(v, str) and v.strip() and len(v) <= 60):
                errors[key] = key + " must be a non-blank string of at most 60 characters"
    for dkey in ("lease_start", "in_service"):
        if dkey not in fields:
            continue
        v = fields[dkey]
        if v is not None:
            try:
                if not isinstance(v, str) or len(v) != 10:
                    raise ValueError(v)
                dt.date.fromisoformat(v)
            except ValueError:
                errors[dkey] = dkey + " must be a valid date like YYYY-MM-DD"
    for ckey in ("lease_monthly_cents", "purchase_cents"):
        if ckey in fields:
            v = fields[ckey]
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v <= 0):
                errors[ckey] = ckey + " must be a positive integer"
    if "acquisition" in fields:
        v = fields["acquisition"]
        if v is not None and v not in ACQUISITIONS:
            errors["acquisition"] = "acquisition must be leased or purchased"
    return errors


def upsert_profile(db, machine_id, fields, now):
    if not isinstance(machine_id, str) or not bloom_ingest.MID_RE.match(machine_id):
        raise ValueError(f"invalid machine_id: {machine_id!r}")
    errors = validate_profile(fields)
    if errors:
        raise ValueError(str(errors))
    create_table(db)
    db.execute("INSERT OR IGNORE INTO machine_profiles (machine_id, updated_at) VALUES (?, ?)", (machine_id, int(now)))
    for key, value in fields.items():
        db.execute("UPDATE machine_profiles SET " + key + " = ? WHERE machine_id = ?",
                   (value.strip() if isinstance(value, str) else value, machine_id))
    db.execute("UPDATE machine_profiles SET active = 1, updated_at = ? WHERE machine_id = ?", (int(now), machine_id))
    db.commit()
    return list_profiles(db)[machine_id]


def deactivate_profile(db, machine_id, now):
    if not isinstance(machine_id, str) or not bloom_ingest.MID_RE.match(machine_id):
        raise ValueError(f"invalid machine_id: {machine_id!r}")
    create_table(db)
    db.execute("INSERT OR IGNORE INTO machine_profiles (machine_id, updated_at) VALUES (?, ?)", (machine_id, int(now)))
    db.execute("UPDATE machine_profiles SET active = 0, updated_at = ? WHERE machine_id = ?", (int(now), machine_id))
    db.commit()
    return None


def list_profiles(db):
    create_table(db)
    out = {}
    for mid, name, model, start, cents, active, acq, ins, pc in db.execute(
            "SELECT machine_id, display_name, model, lease_start, lease_monthly_cents, active, acquisition, in_service,"
            " purchase_cents FROM machine_profiles"):
        out[mid] = {"display_name": name, "model": model, "lease_start": start, "lease_monthly_cents": cents,
                    "acquisition": acq or "leased", "in_service": ins, "purchase_cents": pc, "active": bool(active)}
    return out


def profile_post(path, body, db, machines_path, now):
    """Handle POST /v1/settings/machines/profile and /v1/settings/machines/remove; returns (status, json-able object).

    profile: body {"id": ..., plus any of FIELDS} saves the profile and answers 200 {"id", "profile"}.
    remove:  body {"id": ...} revokes the machine's ingest token and marks the profile inactive; every stored
    row for that machine stays. Answers 200 {"id", "removed": true}."""
    import json
    import bloom_settings
    if path not in ("/v1/settings/machines/profile", "/v1/settings/machines/remove"):
        return (404, {"error": "not found"})
    try:
        data = json.loads(body)
    except Exception:
        return (400, {"error": "bad request"})
    if not isinstance(data, dict):
        return (400, {"error": "bad request"})
    mid = data.get("id")
    if not isinstance(mid, str) or not bloom_ingest.MID_RE.match(mid):
        return (400, {"error": "bad request"})
    if path.endswith("/remove"):
        bloom_settings.revoke_machine(machines_path, mid)
        deactivate_profile(db, mid, now)
        return (200, {"id": mid, "removed": True})
    fields = {k: v for k, v in data.items() if k != "id"}
    errors = validate_profile(fields)
    if errors:
        return (400, {"error": "bad fields", "fields": errors})
    return (200, {"id": mid, "profile": upsert_profile(db, mid, fields, now)})
