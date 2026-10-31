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
    """One archived earnings JSONL line -> dict(ledger_id, ts, micro_usd, kind, model, job_id, completion_tokens), or None."""
    try:
        e = json.loads(line)
        ts = int(dt.datetime.fromisoformat(str(e.get("created_at")).replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError, AttributeError):
        return None
    lid = e.get("_id") or e.get("id")
    amt = e.get("amount_micro_usd")
    if not isinstance(lid, str) or not lid or isinstance(amt, bool) or not isinstance(amt, int) or amt < 0:
        return None
    jid = e.get("job_id")
    kind = "base" if e.get("model") == "base_reward" or str(jid).startswith("floor:") else "job"
    ctok = e.get("completion_tokens")
    return {"ledger_id": lid, "ts": ts, "micro_usd": amt, "kind": kind, "model": e.get("model"), "job_id": jid,
            "completion_tokens": ctok if isinstance(ctok, int) and not isinstance(ctok, bool) else 0}


INGEST_FROM_TS = int(dt.datetime(2026, 10, 13, tzinfo=dt.timezone.utc).timestamp())  # default ingest start, 2026-10-13 UTC


def store_earnings(db, machine_id, sha, payload, since_ts=INGEST_FROM_TS):
    """Parse an earnings JSONL payload into the earnings table; returns (stored, bad)."""
    stored = bad = 0
    for line in payload.splitlines():
        if not line.strip():
            continue
        row = parse_earnings_line(line)
        if row is None:
            bad += 1
        elif row["ts"] >= since_ts:
            cur = db.execute("INSERT OR IGNORE INTO earnings (ledger_id, ts, micro_usd, kind, model, job_id, completion_tokens,"
                             " source_machine) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             (row["ledger_id"], row["ts"], row["micro_usd"], row["kind"], row["model"], row["job_id"],
                              row["completion_tokens"], machine_id))
            stored += cur.rowcount
    if bad:
        db.execute("INSERT OR REPLACE INTO acct_parse_errors (machine_id, sha256, n) VALUES (?, ?, ?)", (machine_id, sha, bad))
    db.commit()
    return stored, bad


def parse_totals_line(line):
    """Parse one JSON line of account totals snapshot -\u003e dict or None."""
    try:
        obj = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    at = obj.get("at")
    if not isinstance(at, str) or not at:
        return None
    count = obj.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        count = None
    total = obj.get("total_micro_usd")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        total = None
    avail = obj.get("available_balance_micro_usd")
    if isinstance(avail, bool) or not isinstance(avail, int) or avail < 0:
        avail = None
    wd = obj.get("withdrawable_balance_micro_usd")
    if isinstance(wd, bool) or not isinstance(wd, int) or wd < 0:
        wd = None
    return {"at": at, "count": count, "total_micro_usd": total,
            "available_micro_usd": avail, "withdrawable_micro_usd": wd}


def store_totals(db, payload):
    """Parse a JSONL payload into account_totals; returns accepted row count."""
    accepted = 0
    for line in payload.splitlines():
        if not line.strip():
            continue
        row = parse_totals_line(line)
        if row is not None:
            db.execute(
                "INSERT OR REPLACE INTO account_totals (at, count, total_micro_usd, "                "available_micro_usd, withdrawable_micro_usd) VALUES (?, ?, ?, ?, ?)",
                (row["at"], row["count"], row["total_micro_usd"],
                 row["available_micro_usd"], row["withdrawable_micro_usd"]))
            accepted += 1
    db.commit()
    return accepted
