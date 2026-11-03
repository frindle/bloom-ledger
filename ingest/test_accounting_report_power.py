"""Frozen test: day_rows also carries metered watt-hours and paid minutes."""
import datetime as dt
import sqlite3

import bloom_accounting_index as AX
import bloom_accounting_report as RP

TZ = "America/Los_Angeles"


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def make():
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    P = "INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, other_work, tokens_delta) VALUES (?,?,?,60,?,?,?)"
    for r in [("m4", utc(2026, 10, 20, 20, 0), 2.5, 1, 0, 5), ("m4", utc(2026, 10, 20, 20, 1), 1.5, 1, 0, 0),
              ("m4", utc(2026, 10, 20, 20, 2), 9.0, 0, 0, 5), ("m5", utc(2026, 10, 20, 20, 3), 4.0, 1, 1, 7),
              ("m4", utc(2026, 10, 22, 20, 0), 1.0, 1, 0, 1)]:
        db.execute(P, r)
    db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, completion_tokens, source_machine) VALUES ('e', ?, 10, 'job', 4, 'm4')",
               (utc(2026, 10, 20, 21, 0),))
    db.commit()
    return db


def test_power_fields_per_day():
    rows = RP.day_rows(make(), TZ, "2026-10-20", "2026-10-22")
    assert [r["date"] for r in rows] == ["2026-10-22", "2026-10-20"]
    d = rows[1]
    assert d["earned_micro"] == 10 and d["tokens"] == 4
    assert d["wh"] == 8.0 and d["minutes"] == 3 and d["paid_minutes"] == 1
    assert rows[0] == {"date": "2026-10-22", "earned_micro": 0, "gpu_micro": 0, "gpu_cost_micro": 0, "gpu_minutes": 1, "other_minutes": 0, "sandbox_micro": 0, "sandbox_cost_micro": 0, "sandbox_minutes": 0, "tokens": 0, "wh": 1.0, "minutes": 1, "paid_minutes": 1, "business_minutes": 1.0, "gpu_bytes_in": 0, "gpu_bytes_out": 0, "sandbox_bytes_in": 0, "sandbox_bytes_out": 0, "total_bytes_in": 0, "total_bytes_out": 0, "net_minutes": 0, "cost_micro": None}


def test_machine_filter_applies_to_power():
    d = RP.day_rows(make(), TZ, "2026-10-20", "2026-10-20", machine="m5")[0]
    assert d["wh"] == 4.0 and d["minutes"] == 1 and d["paid_minutes"] == 0 and d["earned_micro"] == 0


def test_sandbox_job_minute_counts_as_paid():
    db = make()
    db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, other_work, tokens_delta, sandbox_jobs)"
               " VALUES ('m4', ?, 2.0, 60, 1, 0, 0, 1)", (utc(2026, 10, 21, 20, 0),))
    d = RP.day_rows(db, TZ, "2026-10-21", "2026-10-21")[0]
    assert d["minutes"] == 1 and d["paid_minutes"] == 1


def test_sandbox_income_split_out():
    import sqlite3, bloom_accounting_index as AX
    db = sqlite3.connect(":memory:"); AX.create_schema(db)
    cols = [r[1] for r in db.execute("PRAGMA table_info(earnings)")]
    assert "kind" in cols
