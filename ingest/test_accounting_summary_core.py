"""Frozen test: bloom_accounting_summary.build (rows, totals, entries, not-set markers)."""
import datetime as dt
import sqlite3

import bloom_accounting_config as CF
import bloom_accounting_entries as AE
import bloom_accounting_index as AX
import bloom_accounting_summary as SM

SCHED = [{"months": list(range(1, 13)), "periods": [{"start": "00:00", "end": "24:00", "rate": "0.1"}]}]


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def make(rates=True):
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, completion_tokens, source_machine) VALUES ('e', ?, 500, 'job', 9, 'm4')",
               (utc(2026, 10, 20, 20, 0),))
    db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, other_work, tokens_delta) VALUES ('m4', ?, 1000, 60, 1, 0, 3)",
               (utc(2026, 10, 20, 20, 0),))
    db.commit()
    a = AE.add_entry(db, {"kind": "cost", "date": "2026-10-20", "amount_cents": 5, "category": "other"}, 1)
    AE.add_entry(db, {"kind": "cost", "date": "2026-10-21", "amount_cents": 6, "category": "other", "machine_id": "m5"}, 2)
    AE.void_entry(db, a, 3)
    if rates:
        for k, v in (("rate_schedule", SCHED), ("rate_adder_usd_per_kwh", "0"), ("universal_charge_usd_per_kwh", "0"), ("county_fee_pct", "0")):
            CF.set_setting(db, k, v, "2026-10-01", 4)
    return db


def test_month_summary_with_rates():
    s = SM.build(make(), "2026-10-31", "month")
    assert (s["start"], s["end"], s["machine"]) == ("2026-10-01", "2026-10-31", None)
    assert [d["date"] for d in s["days"]] == ["2026-10-20"] and s["totals"]["earned_micro"] == 500 and s["totals"]["cost_micro"] == 100000
    assert s["not_set"] == [] and s["power"] == {"basis": "metered", "estimated": False, "note": "grid rates, solar credit not applied"}
    assert [(e["amount_cents"], e["voided"]) for e in s["entries"]] == [(5, True), (6, False)]


def test_unset_rates_and_machine_filter():
    s = SM.build(make(rates=False), "2026-10-31", "ytd", machine="m4")
    assert s["not_set"] == ["rate_schedule"] and s["totals"]["cost_micro"] is None and s["totals"]["earned_micro"] == 500
    assert [e["amount_cents"] for e in s["entries"]] == [5]
    assert SM.build(make(), "2026-10-31", "day", machine="m5")["power"]["basis"] == "none"
