"""Frozen test: build_tax books pre-tracking earnings, receipts and expensed entries, and fixed costs stop at `through`. Fake numbers."""
import datetime as dt
import sqlite3

import bloom_accounting_config as CF
import bloom_accounting_entries as AE
import bloom_accounting_index as AX
import bloom_accounting_tax as T

SCHED = [{"months": list(range(1, 13)), "periods": [{"start": "00:00", "end": "24:00", "rate": "0.1"}]}]


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def make():
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, completion_tokens, source_machine) VALUES ('e', ?, 2000000, 'job', 9, 'm4')",
               (utc(2026, 10, 20, 20, 0),))
    db.execute("INSERT INTO account_totals (at, count, total_micro_usd) VALUES ('2026-10-13T19:13:39Z', 1, 16515444)")
    for m in (0, 1):
        db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, other_work, tokens_delta) VALUES ('m4', ?, 1000, 60, 1, 0, ?)",
                   (utc(2026, 10, 20, 20, m), 3 if m == 0 else 0))
    db.commit()
    vals = {"rate_schedule": SCHED, "rate_adder_usd_per_kwh": "0", "universal_charge_usd_per_kwh": "0", "county_fee_pct": "0", "m4_machine_id": "m4",
            "m4_in_service_date": "2026-09-28", "dep_method": "straight_line", "dep_life_months": 60,
            "m5_lease_monthly_cents": 1000, "m5_lease_months": 36, "m5_lease_start": "2026-10-01"}
    for k, v in vals.items():
        CF.set_setting(db, k, v, "2026-09-01", 1)
    AE.add_entry(db, {"kind": "cost", "date": "2026-08-13", "amount_cents": 18260, "category": "hardware", "machine_id": "m4"}, 1)
    AE.add_entry(db, {"kind": "cost", "date": "2026-10-05", "amount_cents": 1200, "category": "software", "machine_id": None}, 1)
    AE.add_entry(db, {"kind": "cost", "date": "2026-10-06", "amount_cents": 4000, "category": "internet", "machine_id": None}, 1)
    AE.add_entry(db, {"kind": "receipt", "date": "2026-10-07", "amount_cents": 500, "category": "other", "machine_id": None}, 1)
    return db


def test_pre_tracking_income_lands_in_the_start_month():
    r = T.build_tax(make(), 2026, "business")
    assert r["months"][8]["month"] == "2026-09" and r["months"][8]["income_micro"] == 16515444
    assert r["months"][9]["income_micro"] == 2000000 and r["totals"]["income_micro"] == 16515444 + 2000000
    assert T.build_tax(make(), 2026, "hobby")["totals"] == {"income_micro": 16515444 + 2000000}


def test_receipts_and_entries_count_in_net():
    oct_ = T.build_tax(make(), 2026, "business")["months"][9]
    assert oct_["bp"] == 5000 and oct_["other_income_micro"] == 5000000
    assert oct_["entries_business_micro"] == 1200 * 10000 + 4000 * 5000 // 10000 * 10000
    assert oct_["expenses_micro"] == (oct_["power_business_micro"] + oct_["depreciation_business_micro"] + oct_["lease_business_micro"]
                                      + oct_["entries_business_micro"])
    assert oct_["net_micro"] == 2000000 + 5000000 - oct_["expenses_micro"]


def test_fixed_costs_stop_at_through():
    db = make()
    settings = CF.effective_settings(db, "2026-12-31")["values"]
    shares = {"2026-10": {"bp": 10000}, "2026-11": {"bp": 10000}}
    got = T.fixed_by_month(settings, AE.current_entries(db), 2026, shares, through="2026-10-15")
    assert got["2026-10"]["depreciation_business_cents"] == 18260 * 18 // 1826 - 18260 * 3 // 1826
    full = T.fixed_by_month(settings, AE.current_entries(db), 2026, shares)
    assert full["2026-10"]["depreciation_business_cents"] == 18260 * 34 // 1826 - 18260 * 3 // 1826
    assert got["2026-11"] == full["2026-11"]
    assert "through" in T.fixed_by_month.__doc__ and "pre_tracking_micro" in T.build_tax.__doc__
