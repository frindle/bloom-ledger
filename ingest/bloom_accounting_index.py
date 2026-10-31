"""Accounting index for the bloom-ledger ingest (stdlib only): derived, rebuildable sqlite tables parsed from the
write-once log objects. Money is integer micro-USD or cents. Bookkeeping estimates, not tax advice."""

import re

_ROUTES = (
    (re.compile(r"^power/power-log-\d{4}-\d{2}\.csv\Z"), "power"),
    (re.compile(r"^earnings-archive/totals\.jsonl\Z"), "totals"),
    (re.compile(r"^earnings-archive/[^/]+\.jsonl\Z"), "earnings"),
)

TABLES = ("power_minutes", "earnings", "account_totals", "acct_cursor", "acct_parse_errors")

_DDL = (
    "CREATE TABLE IF NOT EXISTS power_minutes (machine_id TEXT NOT NULL, ts INTEGER NOT NULL, wh REAL, interval_s REAL,"
    " power_ok INTEGER, dbk_state TEXT, other_work INTEGER, tokens_delta INTEGER, PRIMARY KEY (machine_id, ts))",
    "CREATE TABLE IF NOT EXISTS earnings (ledger_id TEXT PRIMARY KEY, ts INTEGER NOT NULL, micro_usd INTEGER NOT NULL,"
    " kind TEXT, model TEXT, job_id TEXT, completion_tokens INTEGER, source_machine TEXT)",
    "CREATE TABLE IF NOT EXISTS account_totals (at TEXT PRIMARY KEY, count INTEGER, total_micro_usd INTEGER,"
    " available_micro_usd INTEGER, withdrawable_micro_usd INTEGER)",
    "CREATE TABLE IF NOT EXISTS acct_cursor (machine_id TEXT NOT NULL, sha256 TEXT NOT NULL,"
    " PRIMARY KEY (machine_id, sha256))",
    "CREATE TABLE IF NOT EXISTS acct_parse_errors (machine_id TEXT NOT NULL, sha256 TEXT NOT NULL, n INTEGER NOT NULL,"
    " PRIMARY KEY (machine_id, sha256))",
)


def create_schema(db):
    for ddl in _DDL:
        db.execute(ddl)
    db.commit()


def reset(db):
    for t in TABLES:
        db.execute("DROP TABLE IF EXISTS " + t)
    create_schema(db)


def route(path):
    """Map an object's meta path to 'power', 'earnings', 'totals' or None."""
    if not isinstance(path, str):
        return None
    for pattern, name in _ROUTES:
        if pattern.match(path):
            return name
    return None


def is_parsed(db, machine_id, sha):
    """True when mark_parsed was called for this (machine_id, sha)."""
    row = db.execute(
        "SELECT 1 FROM acct_cursor WHERE machine_id=? AND sha256=?",
        (machine_id, sha),
    ).fetchone()
    return row is not None


def mark_parsed(db, machine_id, sha):
    """Record (machine_id, sha) as parsed; calling twice is harmless."""
    db.execute(
        "INSERT OR IGNORE INTO acct_cursor (machine_id, sha256) VALUES (?, ?)",
        (machine_id, sha),
    )
    db.commit()
