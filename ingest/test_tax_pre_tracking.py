"""Frozen test: bloom_accounting_tax.pre_tracking_micro (earnings from before per-job tracking began). Fake numbers."""
import datetime as dt
import sqlite3

import bloom_accounting_index as AX
import bloom_accounting_tax as T


def fn(name):
    f = getattr(T, name, None)
    assert callable(f), "bloom_accounting_tax." + name + " is missing"
    return f


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def make(first_total=16515444):
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    for at, total in (("2026-10-14T00:00:00Z", 30000000), ("2026-10-13T19:13:39Z", first_total)):
        db.execute("INSERT INTO account_totals (at, count, total_micro_usd) VALUES (?, 1, ?)", (at, total))
    for i, (ts, micro) in enumerate(((utc(2026, 10, 13, 19, 0), 515444), (utc(2026, 10, 13, 19, 13, 39), 1000), (utc(2026, 10, 13, 19, 14), 900000))):
        db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind) VALUES (?, ?, ?, 'job')", (str(i), ts, micro))
    db.commit()
    return db


def test_first_total_minus_indexed_earnings_up_to_its_time():
    assert fn("pre_tracking_micro")(make(), "2026-09-01", "2026-09-30", "2026-09-28") == 16515444 - 515444 - 1000
    assert fn("pre_tracking_micro")(make(), "2026-09-28", "2026-09-28", "2026-09-28") == 16515444 - 515444 - 1000


def test_only_in_the_period_holding_the_start_date():
    f = fn("pre_tracking_micro")
    assert f(make(), "2026-10-01", "2026-10-31", "2026-09-28") == 0
    assert f(make(), "2026-09-01", "2026-09-27", "2026-09-28") == 0
    assert f(make(), "2026-09-01", "2026-09-30", None) == 0


def test_with_indexed_earnings_it_adds_up_to_the_account_total_without_overlap():
    db = make()
    rows = [{"date": "2026-10-13", "earned_micro": 515444 + 1000 + 900000, "minutes": 1, "paid_minutes": 1, "cost_micro": 0}]
    indexed = T.month_shares(2026, rows)["2026-10"]["income_micro"]
    assert indexed + fn("pre_tracking_micro")(db, "2026-09-01", "2026-09-30", "2026-09-28") == 16515444 + 900000


def test_no_totals_or_negative_gives_zero():
    f = fn("pre_tracking_micro")
    empty = sqlite3.connect(":memory:")
    AX.create_schema(empty)
    assert f(empty, "2026-09-01", "2026-09-30", "2026-09-28") == 0
    assert f(make(first_total=100), "2026-09-01", "2026-09-30", "2026-09-28") == 0
