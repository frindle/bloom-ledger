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
    db.execute("""CREATE TABLE IF NOT EXISTS acct_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        date TEXT NOT NULL,
        amount_cents INTEGER NOT NULL,
        category TEXT NOT NULL,
        machine_id TEXT,
        note TEXT,
        created_at INTEGER NOT NULL,
        voided_at INTEGER
    )""")
    db.commit()


def add_entry(db, entry, created_at):
    err = validate_entry(entry)
    if err is not None:
        raise ValueError(err)
    create_entries_table(db)
    cur = db.execute(
        "INSERT INTO acct_entries (kind, date, amount_cents, category, machine_id, note, created_at, voided_at) "
        "VALUES (:kind, :date, :amount_cents, :category, :machine_id, :note, :created_at, NULL)",
        {
            "kind": entry["kind"],
            "date": entry["date"],
            "amount_cents": entry["amount_cents"],
            "category": entry["category"],
            "machine_id": entry.get("machine_id"),
            "note": entry.get("note"),
            "created_at": created_at,
        },
    )
    db.commit()
    return cur.lastrowid
