"""Accounting index for the bloom-ledger ingest (stdlib only): derived, rebuildable sqlite tables parsed from the
write-once log objects. Money is integer micro-USD or cents. Bookkeeping estimates, not tax advice."""
import datetime as dt
import json
import re

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


_ROUTES = (
    (re.compile(r"^power/power-log-\d{4}-\d{2}\.csv\Z"), "power"),
    (re.compile(r"^earnings-archive/totals\.jsonl\Z"), "totals"),
    (re.compile(r"^earnings-archive/[^/]+\.jsonl\Z"), "earnings"),
)


def route(path):
    if not isinstance(path, str):
        return None
    for rx, name in _ROUTES:
        if rx.match(path):
            return name
    return None


def is_parsed(db, machine_id, sha):
    return db.execute("SELECT 1 FROM acct_cursor WHERE machine_id = ? AND sha256 = ?", (machine_id, sha)).fetchone() is not None


def mark_parsed(db, machine_id, sha):
    db.execute("INSERT OR IGNORE INTO acct_cursor (machine_id, sha256) VALUES (?, ?)", (machine_id, sha))
    db.commit()


def parse_earnings_line(line):
    try:
        obj = json.loads(line)
        if not isinstance(obj, dict):
            return None
    except (json.JSONDecodeError, TypeError):
        return None
    # ledger_id: _id first, else id (must be non-empty str)
    lid = obj.get("_id")
    if not isinstance(lid, str) or not lid:
        lid = obj.get("id")
        if not isinstance(lid, str) or not lid:
            return None
    # created_at → ts (integer epoch seconds)
    raw_ts = obj.get("created_at")
    if raw_ts is None or not isinstance(raw_ts, str):
        return None
    try:
        ts = int(dt.datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError):
        return None
    # micro_usd: amount_micro_usd, must be non-negative int (not bool, not float)
    mu = obj.get("amount_micro_usd")
    if isinstance(mu, bool) or not isinstance(mu, int) or mu < 0:
        return None
    # model and job_id passed through (None when absent)
    model = obj.get("model")
    job_id = obj.get("job_id")
    # kind: 'base' when model == 'base_reward' or job_id starts with 'floor:', else 'job'
    kind = "base" if (model == "base_reward" or (isinstance(job_id, str) and job_id.startswith("floor:"))) else "job"
    # completion_tokens: if int (not bool), use it, else 0
    ct = obj.get("completion_tokens")
    if isinstance(ct, bool) or not isinstance(ct, int):
        ct = 0
    return {"ledger_id": lid, "ts": ts, "micro_usd": mu, "kind": kind, "model": model, "job_id": job_id, "completion_tokens": ct}
