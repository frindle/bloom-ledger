"""Frozen test: day_rows sums per-minute power cost from the user-entered rate schedule."""
import datetime as dt
import sqlite3

import bloom_accounting_index as AX
import bloom_accounting_report as RP

SCHED = [
    {"months": [10, 11, 12, 1, 2, 3, 4, 5], "periods": [{"start": "00:00", "end": "24:00", "rate": "0.08415"}]},
    {"months": [6, 7, 8, 9], "periods": [
        {"start": "00:00", "end": "18:01", "rate": "0.07062"},
        {"start": "18:01", "end": "21:00", "rate": "0.46912"},
        {"start": "21:00", "end": "24:00", "rate": "0.07062"}]},
]
S = {"rate_schedule": SCHED, "rate_adder_usd_per_kwh": "0.00096", "universal_charge_usd_per_kwh": "0.00039",
     "county_fee_pct": "5", "local_timezone": "America/Los_Angeles"}
TZ = "America/Los_Angeles"


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def make(rows):
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    for ts, wh, ok in rows:
        db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, other_work, tokens_delta) VALUES ('m4',?,?,60,?,0,0)", (ts, wh, ok))
    db.commit()
    return db


def test_winter_and_summer_peak_minutes_sum():
    db = make([(utc(2026, 1, 15, 20, 0), 1000, 1), (utc(2026, 1, 15, 20, 1), 1000, 1), (utc(2026, 7, 16, 2, 0), 1000, 1), (utc(2026, 7, 15, 19, 0), 1000, 1)])
    assert RP.day_rows(db, TZ, "2026-01-15", "2026-01-15", settings=S)[0]["cost_micro"] == 2 * 89756
    jul = RP.day_rows(db, TZ, "2026-07-15", "2026-07-15", settings=S)[0]
    assert jul["cost_micro"] == 493974 + 75549 and jul["wh"] == 2000.0


def test_unset_inputs_give_none_and_unmetered_costs_nothing():
    db = make([(utc(2026, 1, 15, 20, 0), 1000, 1), (utc(2026, 1, 15, 20, 1), 5000, 0)])
    assert RP.day_rows(db, TZ, "2026-01-15", "2026-01-15")[0]["cost_micro"] is None
    assert RP.day_rows(db, TZ, "2026-01-15", "2026-01-15", settings=dict(S, county_fee_pct=None))[0]["cost_micro"] is None
    assert RP.day_rows(db, TZ, "2026-01-15", "2026-01-15", settings=S)[0]["cost_micro"] == 89756
