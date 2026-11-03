"""Accounting entries: validated cost and receipt entries kept in an append-only sqlite table (never edited, only voided).

Not tax advice. Money is integer cents; dates are YYYY-MM-DD."""
import datetime as dt


KINDS = ("cost", "receipt")
CATEGORIES = ("hardware", "software", "internet", "electricity", "supplies", "other")

RECORD_COLUMNS = (("vendor", "TEXT"), ("purpose", "TEXT"), ("business_pct", "INTEGER NOT NULL DEFAULT 100"), ("receipt", "TEXT"))
ENTRY_KEYS = ("id", "kind", "date", "amount_cents", "category", "machine_id", "note", "vendor", "purpose", "business_pct", "receipt")


def validate_entry(e):
    """None when `e` is a valid entry dict, else a short error string.
    Optional non-blank strings: vendor (who was paid) and purpose (business purpose), each at most 200 characters.
    Whole-number business-use percent: business_pct from 1 to 100."""
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
    for key in ("vendor", "purpose"):
        val = e.get(key)
        if val is not None:
            if not isinstance(val, str) or len(val.strip()) == 0 or len(val) > 200:
                return "bad " + key
    bpct = e.get("business_pct")
    if bpct is not None:
        if isinstance(bpct, bool) or not isinstance(bpct, int) or bpct < 1 or bpct > 100:
            return "bad business_pct"
    return None


def create_entries_table(db):
    """Create the acct_entries table if it does not exist, then add the tax-record columns
    (vendor, purpose, business_pct, receipt) to an older table."""
    db.execute("CREATE TABLE IF NOT EXISTS acct_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,"
               " date TEXT NOT NULL, amount_cents INTEGER NOT NULL, category TEXT NOT NULL, machine_id TEXT, note TEXT,"
               " created_at INTEGER NOT NULL, voided_at INTEGER)")
    existing = {r[1] for r in db.execute("PRAGMA table_info(acct_entries)").fetchall()}
    for name, decl in RECORD_COLUMNS:
        if name not in existing:
            db.execute(f"ALTER TABLE acct_entries ADD COLUMN {name} {decl}")
    db.commit()


def add_entry(db, entry, created_at):
    """Insert a validated entry and return its new integer id; ValueError(error string) when invalid."""
    err = validate_entry(entry)
    if err:
        raise ValueError(err)
    create_entries_table(db)
    bpct = entry.get("business_pct")
    if bpct is None:
        bpct = 100
    cur = db.execute("INSERT INTO acct_entries (kind, date, amount_cents, category, machine_id, note, created_at,"
                     " vendor, purpose, business_pct, receipt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (entry["kind"], entry["date"], entry["amount_cents"], entry["category"],
                      entry.get("machine_id"), entry.get("note"), created_at,
                      entry.get("vendor"), entry.get("purpose"), bpct, None))
    db.commit()
    return cur.lastrowid


def void_entry(db, entry_id, voided_at):
    """Mark a live entry voided (kept for audit). True when a live row was voided, False when missing or already void."""
    create_entries_table(db)
    cur = db.execute("UPDATE acct_entries SET voided_at = ? WHERE id = ? AND voided_at IS NULL", (voided_at, entry_id))
    db.commit()
    return cur.rowcount == 1


def attach_receipt(db, entry_id, name):
    r"""Record the stored receipt file name on a live entry.

    Returns True when a row was updated, False for missing or voided entries.
    The name must be a plain file name with no path separators (no / or \ characters)
    and must not start with a dot."""
    if not isinstance(name, str) or not name or len(name) > 200 or '/' in name or '\\' in name or name.startswith('.'):
        raise ValueError("bad receipt")
    create_entries_table(db)
    cur = db.execute("UPDATE acct_entries SET receipt = ? WHERE id = ? AND voided_at IS NULL", (name, entry_id))
    db.commit()
    return cur.rowcount == 1


def all_entries(db, start=None, end=None):
    """Non-filtered-on-void entries as dicts (id, kind, date, amount_cents, category, machine_id, note, vendor,
    purpose, business_pct, receipt, voided), ordered by date then id. start/end are optional inclusive
    YYYY-MM-DD bounds."""
    create_entries_table(db)
    sql = "SELECT id, kind, date, amount_cents, category, machine_id, note, vendor, purpose,"
    sql += " business_pct, receipt, voided_at FROM acct_entries"
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
    keys = ENTRY_KEYS
    rows = db.execute(sql, args).fetchall()
    return [dict(zip(keys, r[:len(keys)])) | {"voided": r[len(keys)] is not None} for r in rows]


def current_entries(db, start=None, end=None):
    """Non-voided entries as dicts (id, kind, date, amount_cents, category, machine_id, note, vendor,
    purpose, business_pct, receipt), ordered by date then id. start/end are optional inclusive
    YYYY-MM-DD bounds."""
    create_entries_table(db)
    sql = "SELECT id, kind, date, amount_cents, category, machine_id, note, vendor, purpose,"
    sql += " business_pct, receipt FROM acct_entries WHERE voided_at IS NULL"
    args = []
    if start is not None:
        sql += " AND date >= ?"
        args.append(start)
    if end is not None:
        sql += " AND date <= ?"
        args.append(end)
    sql += " ORDER BY date, id"
    keys = ENTRY_KEYS
    return [dict(zip(keys, r)) for r in db.execute(sql, args).fetchall()]
