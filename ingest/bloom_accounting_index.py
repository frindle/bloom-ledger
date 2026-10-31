"""Accounting index for the bloom-ledger ingest (stdlib only): derived, rebuildable sqlite tables parsed from the
write-once log objects. Money is integer micro-USD or cents. Bookkeeping estimates, not tax advice."""

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
    """Create every table in TABLES if missing (idempotent)."""
    for stmt in _DDL:
        db.execute(stmt)
    db.commit()


def reset(db):
    """Drop and recreate the derived tables in TABLES; never touch any other table."""
    for name in TABLES:
        db.execute(f"DROP TABLE IF EXISTS {name}")
    create_schema(db)
