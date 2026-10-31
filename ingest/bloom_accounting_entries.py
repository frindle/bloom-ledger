"""Accounting entries: validated cost and receipt entries kept in an append-only sqlite table (never edited, only voided).

Not tax advice. Money is integer cents; dates are YYYY-MM-DD."""
import datetime as dt


KINDS = ("cost", "receipt")
CATEGORIES = ("hardware", "software", "internet", "electricity", "supplies", "other")


def validate_entry(e):
    """None when `e` is a valid entry dict, else a short error string."""
    if not isinstance(e, dict):
        return "not an object"
    if e.get("kind") not in KINDS:
        return "bad kind"
    d = e.get("date")
    if not isinstance(d, str) or len(d) != 10:
        return "bad date"
    try:
        dt.date.fromisoformat(d)
    except ValueError:
        return "bad date"
    amt = e.get("amount_cents")
    if isinstance(amt, bool) or not isinstance(amt, int) or amt <= 0:
        return "bad amount"
    if e.get("category") not in CATEGORIES:
        return "bad category"
    mid = e.get("machine_id")
    if mid is not None and (not isinstance(mid, str) or not mid):
        return "bad machine_id"
    note = e.get("note")
    if note is not None and not isinstance(note, str):
        return "bad note"
    return None


def create_entries_table(db):
    db.execute("CREATE TABLE IF NOT EXISTS acct_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,"
               " date TEXT NOT NULL, amount_cents INTEGER NOT NULL, category TEXT NOT NULL, machine_id TEXT, note TEXT,"
               " created_at INTEGER NOT NULL, voided_at INTEGER)")
    db.commit()


def add_entry(db, entry, created_at):
    """Insert a validated entry and return its new integer id; ValueError(error string) when invalid."""
    err = validate_entry(entry)
    if err:
        raise ValueError(err)
    create_entries_table(db)
    cur = db.execute("INSERT INTO acct_entries (kind, date, amount_cents, category, machine_id, note, created_at)"
                     " VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (entry["kind"], entry["date"], entry["amount_cents"], entry["category"],
                      entry.get("machine_id"), entry.get("note"), created_at))
    db.commit()
    return cur.lastrowid


def void_entry(db, entry_id, voided_at):
    """Mark a live entry voided (kept for audit). True when a live row was voided, False when missing or already void."""
    create_entries_table(db)
    cur = db.execute("UPDATE acct_entries SET voided_at = ? WHERE id = ? AND voided_at IS NULL", (voided_at, entry_id))
    db.commit()
    return cur.rowcount == 1


def all_entries(db, start=None, end=None):
    """Non-filtered-on-void entries as dicts (id, kind, date, amount_cents, category, machine_id, note, voided),
    ordered by date then id. start/end are optional inclusive YYYY-MM-DD bounds."""
    create_entries_table(db)
    sql = "SELECT id, kind, date, amount_cents, category, machine_id, note, voided_at FROM acct_entries"
    args = []
    filters = []
    if start is not None:
        filters.append("date >= ?")
        args.append(start)
    if end is not None:
        filters.append("date <= ?")
        args.append(end)
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " ORDER BY date, id"
    keys = ("id", "kind", "date", "amount_cents", "category", "machine_id", "note", "voided_at")
    rows = db.execute(sql, args).fetchall()
    return [dict(zip(keys[:-1], r[:-1])) | {"voided": r[-1] is not None} for r in rows]


def current_entries(db, start=None, end=None):
    """Non-voided entries as dicts (id, kind, date, amount_cents, category, machine_id, note), ordered by date then id.
    start/end are optional inclusive YYYY-MM-DD bounds."""
    create_entries_table(db)
    sql = "SELECT id, kind, date, amount_cents, category, machine_id, note FROM acct_entries WHERE voided_at IS NULL"
    args = []
    if start is not None:
        sql += " AND date >= ?"
        args.append(start)
    if end is not None:
        sql += " AND date <= ?"
        args.append(end)
    sql += " ORDER BY date, id"
    keys = ("id", "kind", "date", "amount_cents", "category", "machine_id", "note")
    return [dict(zip(keys, r)) for r in db.execute(sql, args).fetchall()]
