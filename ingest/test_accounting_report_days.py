"""Frozen test: bloom_accounting_report.day_rows groups earnings by local day."""
import datetime as dt
import sqlite3

import bloom_accounting_index as AX
import bloom_accounting_report as RP

TZ = "America/Los_Angeles"


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def make(rows):
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    for i, (ts, micro, tok, mach) in enumerate(rows):
        db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, completion_tokens, source_machine) VALUES (?,?,?,?,?,?)",
                   ("l%d" % i, ts, micro, "job", tok, mach))
    db.commit()
    return db


def test_groups_by_local_day_newest_first():
    db = make([(utc(2026, 10, 20, 6, 0), 100, 10, "m4"), (utc(2026, 10, 20, 20, 0), 50, None, "m4"), (utc(2026, 10, 21, 20, 0), 7, 3, "m4")])
    assert RP.day_rows(db, TZ, "2026-10-19", "2026-10-21") == [
        {"date": "2026-10-21", "earned_micro": 7, "tokens": 3},
        {"date": "2026-10-20", "earned_micro": 50, "tokens": 0},
        {"date": "2026-10-19", "earned_micro": 100, "tokens": 10}]


def test_range_edges_and_machine_filter():
    db = make([(utc(2026, 10, 20, 7, 0), 1, 1, "m4"), (utc(2026, 10, 21, 6, 59), 2, 1, "m5"), (utc(2026, 10, 21, 7, 0), 4, 1, "m4")])
    assert RP.ts_bounds(TZ, "2026-10-20", "2026-10-20") == (utc(2026, 10, 20, 7, 0), utc(2026, 10, 21, 7, 0))
    assert [r["earned_micro"] for r in RP.day_rows(db, TZ, "2026-10-20", "2026-10-20")] == [3]
    assert RP.day_rows(db, TZ, "2026-10-20", "2026-10-20", machine="m5")[0]["earned_micro"] == 2
    assert RP.day_rows(db, TZ, "2026-10-22", "2026-10-23") == []
