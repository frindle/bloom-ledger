"""Accounting index for the bloom-ledger ingest (stdlib only): derived, rebuildable sqlite tables parsed from the
write-once log objects. Money is integer micro-USD or cents. Bookkeeping estimates, not tax advice."""
import csv
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
    """One totals.jsonl snapshot -> dict(at, count, total_micro_usd, available_micro_usd, withdrawable_micro_usd) or None."""
    try:
        e = json.loads(line)
        at = e.get("at")
    except (ValueError, AttributeError):
        return None
    if not isinstance(at, str) or not at:
        return None

    def num(v):
        return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None
    return {"at": at, "count": num(e.get("count")), "total_micro_usd": num(e.get("total_micro_usd")),
            "available_micro_usd": num(e.get("available_balance_micro_usd")),
            "withdrawable_micro_usd": num(e.get("withdrawable_balance_micro_usd"))}


def store_totals(db, payload):
    """Parse a totals.jsonl payload into account_totals (one row per `at`, last one wins); returns rows stored."""
    n = 0
    for line in payload.splitlines():
        row = parse_totals_line(line) if line.strip() else None
        if row:
            db.execute("INSERT OR REPLACE INTO account_totals (at, count, total_micro_usd, available_micro_usd,"
                       " withdrawable_micro_usd) VALUES (?, ?, ?, ?, ?)", (row["at"], row["count"], row["total_micro_usd"],
                                                                         row["available_micro_usd"], row["withdrawable_micro_usd"]))
            n += 1
    db.commit()
    return n


LEGACY_POWER_COLUMNS = ["ts_utc", "interval_s", "samples", "power_ok", "avg_w", "max_w", "wh", "dbk_up", "dbk_state",
                        "inference_active_frac", "requests_delta", "tokens_delta", "warm_models", "load_transition_active",
                        "gpu_pct", "other_work", "other_procs", "note"]


def power_columns(first_line):
    """Header columns when `first_line` is a power CSV header (has ts_utc and wh), else None."""
    cols = next(csv.reader([first_line.strip()]), [])
    return cols if "ts_utc" in cols and "wh" in cols else None


def parse_power_line(line, columns):
    """One power CSV row -> dict(ts, wh, interval_s, power_ok, dbk_state, other_work, tokens_delta), or None."""
    vals = next(csv.reader([line.strip()]), [])
    if len(vals) < len(columns) or not line.strip():
        return None
    r = dict(zip(columns, vals))
    try:
        ts = int(dt.datetime.fromisoformat(r["ts_utc"].replace("Z", "+00:00")).timestamp())
        ok = 1 if r["power_ok"].strip().lower() in ("1", "true") else 0
        wh = float(r["wh"] or 0) if ok else 0.0
        return {"ts": ts, "wh": wh, "interval_s": float(r["interval_s"] or 0), "power_ok": ok,
                "dbk_state": r.get("dbk_state", ""), "other_work": 1 if float(r.get("other_work") or 0) > 0 else 0,
                "tokens_delta": int(float(r.get("tokens_delta") or 0))}
    except (KeyError, ValueError):
        return None


def store_power(db, machine_id, sha, path, offset, payload, since_ts=INGEST_FROM_TS):
    """Parse a power CSV payload into the power_minutes table; returns (stored, bad)."""
    db.execute(
        "CREATE TABLE IF NOT EXISTS acct_headers ("
        "machine_id TEXT NOT NULL, path TEXT NOT NULL, header TEXT NOT NULL, "
        "PRIMARY KEY (machine_id, path))"
    )
    stored = bad = 0
    non_blank = [l for l in payload.splitlines() if l.strip()]
    columns = LEGACY_POWER_COLUMNS
    if offset == 0 and non_blank:
        hdr = power_columns(non_blank[0])
        if hdr is not None:
            columns = hdr
            db.execute(
                "INSERT OR REPLACE INTO acct_headers (machine_id, path, header) VALUES (?, ?, ?)",
                (machine_id, path, non_blank[0]),
            )
            non_blank = non_blank[1:]
    for line in non_blank:
        row = parse_power_line(line, columns)
        if row is None:
            bad += 1
        elif row["ts"] >= since_ts:
            cur = db.execute(
                "INSERT OR IGNORE INTO power_minutes "
                "(machine_id, ts, wh, interval_s, power_ok, dbk_state, other_work, tokens_delta) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (machine_id, row["ts"], row["wh"], row["interval_s"], row["power_ok"],
                 row["dbk_state"], row["other_work"], row["tokens_delta"]),
            )
            stored += cur.rowcount
    if bad:
        db.execute(
            "INSERT OR REPLACE INTO acct_parse_errors (machine_id, sha256, n) VALUES (?, ?, ?)",
            (machine_id, sha, bad),
        )
    db.commit()
    return stored, bad
