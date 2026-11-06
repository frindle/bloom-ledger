"""Accounting index for the bloom-ledger ingest (stdlib only): derived, rebuildable sqlite tables parsed from the
write-once log objects. Money is integer micro-USD or cents. Bookkeeping estimates, not tax advice."""
from pathlib import Path
import csv
import datetime as dt
import json
import re

TABLES = ("power_minutes", "sandbox_bridge", "net_bridge", "usage_bridge", "earnings", "account_totals", "acct_cursor", "acct_parse_errors")

_DDL = (
    "CREATE TABLE IF NOT EXISTS power_minutes (machine_id TEXT NOT NULL, ts INTEGER NOT NULL, wh REAL, interval_s REAL,"
    " power_ok INTEGER, dbk_state TEXT, other_work INTEGER, tokens_delta INTEGER, sandbox_jobs INTEGER NOT NULL DEFAULT 0,"
    " gpu_bytes_in INTEGER, gpu_bytes_out INTEGER, sandbox_bytes_in INTEGER, sandbox_bytes_out INTEGER,"
    " total_bytes_in INTEGER, total_bytes_out INTEGER, active_frac REAL,"
    " usage_s REAL, dbk_cpu_ms INTEGER, dbk_cpu_mj INTEGER, dbk_gpu_ms INTEGER, sbx_cpu_ms INTEGER, sbx_cpu_mj INTEGER,"
    " sbx_gpu_ms INTEGER, own_cpu_ms INTEGER, own_cpu_mj INTEGER, own_gpu_ms INTEGER, sys_gpu_ms INTEGER, cpu_mj INTEGER,"
    " gpu_mj INTEGER, dbk_local INTEGER, PRIMARY KEY (machine_id, ts))",
    "CREATE TABLE IF NOT EXISTS sandbox_bridge (machine_id TEXT NOT NULL, ts INTEGER NOT NULL, jobs INTEGER NOT NULL,"
    " PRIMARY KEY (machine_id, ts))",
    "CREATE TABLE IF NOT EXISTS net_bridge (machine_id TEXT NOT NULL, ts INTEGER NOT NULL, gpu_bytes_in INTEGER,"
    " gpu_bytes_out INTEGER, sandbox_bytes_in INTEGER, sandbox_bytes_out INTEGER, total_bytes_in INTEGER,"
    " total_bytes_out INTEGER, PRIMARY KEY (machine_id, ts))",
    "CREATE TABLE IF NOT EXISTS usage_bridge (machine_id TEXT NOT NULL, ts INTEGER NOT NULL, usage_s REAL,"
    " dbk_cpu_ms INTEGER, dbk_cpu_mj INTEGER, dbk_gpu_ms INTEGER, sbx_cpu_ms INTEGER, sbx_cpu_mj INTEGER,"
    " sbx_gpu_ms INTEGER, own_cpu_ms INTEGER, own_cpu_mj INTEGER, own_gpu_ms INTEGER, sys_gpu_ms INTEGER,"
    " cpu_mj INTEGER, gpu_mj INTEGER, dbk_local INTEGER, PRIMARY KEY (machine_id, ts))",
    "CREATE TABLE IF NOT EXISTS earnings (ledger_id TEXT PRIMARY KEY, ts INTEGER NOT NULL, micro_usd INTEGER NOT NULL,"
    " kind TEXT, model TEXT, job_id TEXT, completion_tokens INTEGER, source_machine TEXT)",
    "CREATE TABLE IF NOT EXISTS account_totals (at TEXT PRIMARY KEY, count INTEGER, total_micro_usd INTEGER,"
    " available_micro_usd INTEGER, withdrawable_micro_usd INTEGER)",
    "CREATE TABLE IF NOT EXISTS acct_cursor (machine_id TEXT NOT NULL, sha256 TEXT NOT NULL,"
    " PRIMARY KEY (machine_id, sha256))",
    "CREATE TABLE IF NOT EXISTS acct_parse_errors (machine_id TEXT NOT NULL, sha256 TEXT NOT NULL, n INTEGER NOT NULL,"
    " PRIMARY KEY (machine_id, sha256))",
)


INDEX_VERSION = "6"  # bump to rebuild every derived table from the stored raw objects on next start


def create_schema(db):
    db.execute("CREATE TABLE IF NOT EXISTS acct_meta (k TEXT PRIMARY KEY, v TEXT)")
    row = db.execute("SELECT v FROM acct_meta WHERE k = 'index_version'").fetchone()
    if row is None or row[0] != INDEX_VERSION:
        for t in TABLES:
            db.execute("DROP TABLE IF EXISTS " + t)
        db.execute("INSERT OR REPLACE INTO acct_meta (k, v) VALUES ('index_version', ?)", (INDEX_VERSION,))
    for ddl in _DDL:
        db.execute(ddl)
    if "sandbox_jobs" not in [r[1] for r in db.execute("PRAGMA table_info(power_minutes)")]:
        db.execute("ALTER TABLE power_minutes ADD COLUMN sandbox_jobs INTEGER NOT NULL DEFAULT 0")
    db.commit()


def reset(db):
    for t in TABLES:
        db.execute("DROP TABLE IF EXISTS " + t)
    create_schema(db)


_ROUTES = (
    (re.compile(r"^power/power-log-\d{4}-\d{2}\.csv\Z"), "power"),
    (re.compile(r"^power/sandbox-jobs-[a-z]*-?\d{4}-\d{2}\.csv\Z"), "sandbox"),
    (re.compile(r"^power/net-bytes-\d{4}-\d{2}\.csv\Z"), "net"),
    (re.compile(r"^power/usage-\d{4}-\d{2}\.csv\Z"), "usage"),
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
    kind = "base" if e.get("model") == "base_reward" or str(jid).startswith("floor:") else ("sandbox" if (isinstance(e.get("model"), str) and e.get("model").startswith("sandbox:")) or str(jid).startswith("sandbox:") else "job")
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


# Until the sampler fix at this time, every minute was flagged other_work because agent shell wrappers
# (`zsh -c "...pipeline-canary.py..."`) only MENTIONED pipeline-canary.py in their command line. For those rows the
# flag is recomputed from other_procs without that name; later rows are trusted as written.
WRAPPER_FIX_TS = 1793688120  # 2026-11-03T06:42:00Z
WRAPPER_FALSE_POSITIVES = {"pipeline-canary.py"}


# macOS housekeeping daemons that spike CPU on their own schedule. They are not Penn's work, so a minute they
# alone flagged is not other work (the sampler ignores them from 2026-11-03; older rows are recomputed here).
SYSTEM_DAEMONS = ("corespotlightd", "backupd", "XProtect", "mds", "mdworker", "softwareupdated",
                  "photoanalysisd", "mediaanalysisd", "spotlightknowledged")
VM_ENTRY = "cpu>150%:com.apple.Virtualization.VirtualMachine"
VM_ONLY = 2  # other_work value: only a busy VM flagged it; cleared once the minute is known to run a Sandbox job


def _benign(ts, proc):
    if ts < WRAPPER_FIX_TS and proc in WRAPPER_FALSE_POSITIVES:
        return True
    return proc.startswith("cpu>") and any(d in proc.split(":", 1)[-1] for d in SYSTEM_DAEMONS)


def other_work_flag(ts, r):
    """0 = not other work, 1 = other work, VM_ONLY = only the Virtualization VM (the Sandbox's own VM when a job ran)."""
    flagged = float(r.get("other_work") or 0) > 0
    if not flagged or "other_procs" not in r:
        return 1 if flagged else 0
    procs = {p.strip() for p in (r.get("other_procs") or "").split(";") if p.strip()}
    if not procs:
        return 1
    left = {p for p in procs if not _benign(ts, p)}
    if not left:
        return 0
    return VM_ONLY if left == {VM_ENTRY} else 1


# Network bytes moved in each minute (in = received, out = sent), from the sampler. None = not measured, 0 = nothing moved.
NET_COLUMNS = ("gpu_bytes_in", "gpu_bytes_out", "sandbox_bytes_in", "sandbox_bytes_out", "total_bytes_in", "total_bytes_out")


def net_bytes(r, col):
    """A byte count from a sampler row: None when the column is absent, blank (not measured) or not a whole number >= 0."""
    try:
        n = int((r.get(col) or "").strip())
    except ValueError:
        return None
    return n if n >= 0 else None


# Per-minute CPU/GPU use by bucket, from the sampler's usage sidecar (bloom_power_lib.USAGE_COLUMNS): ms of CPU or GPU
# time, mJ of energy, dbk_local 0/1. None = not measured.
USAGE_COLUMNS = ("usage_s", "dbk_cpu_ms", "dbk_cpu_mj", "dbk_gpu_ms", "sbx_cpu_ms", "sbx_cpu_mj", "sbx_gpu_ms",
                 "own_cpu_ms", "own_cpu_mj", "own_gpu_ms", "sys_gpu_ms", "cpu_mj", "gpu_mj", "dbk_local")


def usage_value(r, col):
    """A usage sidecar value: None when absent, blank or not a number >= 0; usage_s stays a float, the rest are ints
    (dbk_local is 1 for any value above 0)."""
    try:
        v = float((r.get(col) or "").strip())
    except ValueError:
        return None
    if v != v or v < 0 or v == float("inf"):
        return None
    if col == "usage_s":
        return v
    return (1 if v > 0 else 0) if col == "dbk_local" else int(round(v))


def active_frac(r):
    """The sampler's inference_active_frac clamped to 0..1, or None when the column is absent, blank or not a number."""
    try:
        f = float((r.get("inference_active_frac") or "").strip())
    except ValueError:
        return None
    return None if f != f else min(1.0, max(0.0, f))


def parse_power_line(line, columns):
    """One power CSV row -> dict(ts, wh, interval_s, power_ok, dbk_state, other_work, tokens_delta, sandbox_jobs), or None."""
    vals = next(csv.reader([line.strip()]), [])
    if len(vals) < len(columns) or not line.strip():
        return None
    r = dict(zip(columns, vals))
    try:
        ts = int(dt.datetime.fromisoformat(r["ts_utc"].replace("Z", "+00:00")).timestamp())
        ok = 1 if r["power_ok"].strip().lower() in ("1", "true") else 0
        wh = float(r["wh"] or 0) if ok else 0.0
        return {"ts": ts, "wh": wh, "interval_s": float(r["interval_s"] or 0), "power_ok": ok,
                "dbk_state": r.get("dbk_state", ""), "other_work": other_work_flag(ts, r),
                "tokens_delta": int(float(r.get("tokens_delta") or 0)),
                "sandbox_jobs": max(0, int(float(r.get("sandbox_jobs") or 0))), "active_frac": active_frac(r),
                **{c: net_bytes(r, c) for c in NET_COLUMNS}}
    except (KeyError, ValueError):
        return None


def store_power(db, machine_id, sha, path, offset, payload, since_ts=INGEST_FROM_TS):
    """Parse a power CSV increment into power_minutes; returns (stored, bad). Header comes from the offset-0 object."""
    db.execute("CREATE TABLE IF NOT EXISTS acct_headers (machine_id TEXT NOT NULL, path TEXT NOT NULL, header TEXT NOT NULL,"
               " PRIMARY KEY (machine_id, path))")
    lines = [ln for ln in payload.splitlines() if ln.strip()]
    if offset == 0 and lines and power_columns(lines[0]):
        db.execute("INSERT OR REPLACE INTO acct_headers (machine_id, path, header) VALUES (?, ?, ?)",
                   (machine_id, path, lines[0]))
        lines = lines[1:]
    hdr = db.execute("SELECT header FROM acct_headers WHERE machine_id = ? AND path = ?", (machine_id, path)).fetchone()
    cols = power_columns(hdr[0]) if hdr else LEGACY_POWER_COLUMNS
    stored = bad = 0
    for ln in lines:
        r = parse_power_line(ln, cols)
        if r is None:
            bad += 1
        elif r["ts"] >= since_ts:
            cur = db.execute("INSERT OR IGNORE INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, dbk_state,"
                             " other_work, tokens_delta, sandbox_jobs, active_frac, " + ", ".join(NET_COLUMNS) + ") VALUES ("
                             + ", ".join("?" * (10 + len(NET_COLUMNS))) + ")",
                             (machine_id, r["ts"], r["wh"], r["interval_s"], r["power_ok"], r["dbk_state"],
                              r["other_work"], r["tokens_delta"], r["sandbox_jobs"], r["active_frac"], *[r[c] for c in NET_COLUMNS]))
            stored += cur.rowcount
    if bad:
        db.execute("INSERT OR REPLACE INTO acct_parse_errors (machine_id, sha256, n) VALUES (?, ?, ?)", (machine_id, sha, bad))
    db.commit()
    return stored, bad


def store_sandbox(db, machine_id, payload):
    """Sandbox-jobs sidecar rows (ts_utc,sandbox_jobs) -> sandbox_bridge, then copy onto the matching power_minutes rows.
    The sampler writes the sidecar while a month's power CSV header predates the sandbox_jobs column."""
    for ln in payload.splitlines():
        a = ln.strip().split(",")
        if len(a) != 2 or a[0] == "ts_utc":
            continue
        try:
            ts = int(dt.datetime.fromisoformat(a[0].replace("Z", "+00:00")).timestamp())
            jobs = max(0, int(float(a[1])))
        except ValueError:
            continue
        db.execute("INSERT OR REPLACE INTO sandbox_bridge (machine_id, ts, jobs) VALUES (?, ?, ?)", (machine_id, ts, jobs))
    apply_sandbox_bridge(db)


def apply_sandbox_bridge(db):
    db.execute("UPDATE power_minutes SET sandbox_jobs = (SELECT b.jobs FROM sandbox_bridge b WHERE b.machine_id = power_minutes.machine_id"
               " AND b.ts = power_minutes.ts) WHERE sandbox_jobs = 0 AND EXISTS (SELECT 1 FROM sandbox_bridge b"
               " WHERE b.machine_id = power_minutes.machine_id AND b.ts = power_minutes.ts AND b.jobs > 0)")
    db.execute("UPDATE power_minutes SET other_work = 0 WHERE other_work = ? AND sandbox_jobs > 0", (VM_ONLY,))
    db.commit()


def store_net(db, machine_id, payload):
    """Net-bytes sidecar rows -> net_bridge (by header name; a headerless increment uses the sidecar order), then power_minutes."""
    cols = ["ts_utc", *NET_COLUMNS]
    for vals in csv.reader(payload.splitlines()):
        if vals and vals[0] == "ts_utc":
            cols = vals
            continue
        r = dict(zip(cols, vals))
        try:
            ts = int(dt.datetime.fromisoformat((r.get("ts_utc") or "").replace("Z", "+00:00")).timestamp())
        except ValueError:
            continue
        db.execute("INSERT OR REPLACE INTO net_bridge (machine_id, ts, " + ", ".join(NET_COLUMNS) + ") VALUES (?, ?"
                   + ", ?" * len(NET_COLUMNS) + ")", (machine_id, ts, *[net_bytes(r, c) for c in NET_COLUMNS]))
    apply_net_bridge(db)


def apply_net_bridge(db):
    """Fill power_minutes byte columns that are still NULL from net_bridge (same machine and minute)."""
    for c in NET_COLUMNS:
        db.execute(f"UPDATE power_minutes SET {c} = (SELECT b.{c} FROM net_bridge b WHERE b.machine_id = power_minutes.machine_id"
                   f" AND b.ts = power_minutes.ts) WHERE {c} IS NULL")
    db.commit()


def store_usage(db, machine_id, payload):
    """Usage sidecar rows -> usage_bridge (by header name; a headerless increment uses the sidecar order), then
    power_minutes."""
    cols = ["ts_utc", *USAGE_COLUMNS]
    for vals in csv.reader(payload.splitlines()):
        if vals and vals[0] == "ts_utc":
            cols = vals
            continue
        r = dict(zip(cols, vals))
        try:
            ts = int(dt.datetime.fromisoformat((r.get("ts_utc") or "").replace("Z", "+00:00")).timestamp())
        except ValueError:
            continue
        db.execute("INSERT OR REPLACE INTO usage_bridge (machine_id, ts, " + ", ".join(USAGE_COLUMNS) + ") VALUES (?, ?"
                   + ", ?" * len(USAGE_COLUMNS) + ")", (machine_id, ts, *[usage_value(r, c) for c in USAGE_COLUMNS]))
    apply_usage_bridge(db)


def apply_usage_bridge(db):
    """Fill power_minutes usage columns that are still NULL from usage_bridge (same machine and minute)."""
    for c in USAGE_COLUMNS:
        db.execute(f"UPDATE power_minutes SET {c} = (SELECT b.{c} FROM usage_bridge b WHERE b.machine_id = power_minutes.machine_id"
                   f" AND b.ts = power_minutes.ts) WHERE {c} IS NULL")
    db.commit()


def index_new(db, root):
    """Parse every not-yet-parsed `log` object into the derived tables; returns the number of objects handled."""
    n = 0
    rows = db.execute("SELECT machine_id, sha256 FROM objects WHERE kind = 'log' ORDER BY received_at, rowid").fetchall()
    for machine_id, sha in rows:
        if is_parsed(db, machine_id, sha):
            continue
        try:
            raw = (Path(root) / "objects" / machine_id / "log" / (sha + ".obj")).read_bytes()
            head, _, body = raw.partition(b"\n")
            meta = json.loads(head)
            path = meta["path"]
            offset = int(meta.get("offset") or 0)
        except (OSError, ValueError, KeyError, TypeError):
            mark_parsed(db, machine_id, sha)
            continue
        text = body.decode("utf-8", "replace")
        kind = route(path)
        if kind == "earnings":
            store_earnings(db, machine_id, sha, text)
        elif kind == "totals":
            store_totals(db, text)
        elif kind == "power":
            store_power(db, machine_id, sha, path, offset, text)
            apply_sandbox_bridge(db)
            apply_net_bridge(db)
            apply_usage_bridge(db)
        elif kind == "sandbox":
            store_sandbox(db, machine_id, text)
        elif kind == "net":
            store_net(db, machine_id, text)
        elif kind == "usage":
            store_usage(db, machine_id, text)
        mark_parsed(db, machine_id, sha)
        n += 1
    return n
