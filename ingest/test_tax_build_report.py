"""Frozen test: bloom_accounting_tax.build_tax (whole-year report from the database). Fake numbers."""
import datetime as dt
import sqlite3

import pytest

import bloom_accounting_config as CF
import bloom_accounting_entries as AE
import bloom_accounting_index as AX
import bloom_accounting_tax as T

SCHED = [{"months": list(range(1, 13)), "periods": [{"start": "00:00", "end": "24:00", "rate": "0.1"}]}]


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def make(rates=True):
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    for ts, micro in ((utc(2026, 10, 20, 20, 0), 2000000), (utc(2025, 10, 20, 20, 0), 777000)):
        db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, completion_tokens, source_machine) VALUES (?, ?, ?, 'job', 9, 'm4')",
                   (str(ts), ts, micro))
    for m, tok, other in ((0, 3, 0), (1, 0, 0), (2, 5, 1)):
        db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, other_work, tokens_delta) VALUES ('m4', ?, 1000, 60, 1, ?, ?)",
                   (utc(2026, 10, 20, 20, m), other, tok))
    db.commit()
    vals = {"rate_adder_usd_per_kwh": "0", "universal_charge_usd_per_kwh": "0", "county_fee_pct": "0", "m4_machine_id": "m4",
            "m4_in_service_date": "2026-10-01", "dep_life_months": 60, "m5_lease_monthly_cents": 1000, "m5_lease_months": 36,
            "m5_lease_start": "2026-10-01"}
    if rates:
        vals["rate_schedule"] = SCHED
    for k, v in vals.items():
        CF.set_setting(db, k, v, "2026-10-01", 1)
    AE.add_entry(db, {"kind": "cost", "date": "2026-08-13", "amount_cents": 18260, "category": "hardware", "machine_id": "m4"}, 1)
    return db


def test_business_year_report():
    r = T.build_tax(make(), 2026, "business")
    assert r["year"] == 2026 and r["view"] == "business" and r["disclaimer"] == "Bookkeeping, not tax advice"
    assert [m["month"] for m in r["months"]] == ["2026-%02d" % i for i in range(1, 13)]
    oct_ = r["months"][9]
    assert oct_["income_micro"] == 2000000 and oct_["bp"] == 3333
    assert oct_["power_business_micro"] == 300000 * 3333 // 10000
    assert oct_["depreciation_business_micro"] == 18260 * 31 // 1826 * 3333 // 10000 * 10000
    assert oct_["lease_business_micro"] == 1000 * 12 * 31 // 365 * 3333 // 10000 * 10000
    assert r["months"][10]["expenses_micro"] == 0 and r["months"][10]["net_micro"] == 0
    assert r["totals"]["income_micro"] == 2000000 and r["totals"]["net_micro"] == 2000000 - oct_["expenses_micro"]


def test_hobby_view_is_income_only_and_bad_view_raises():
    r = T.build_tax(make(rates=False), 2026, "hobby")
    assert r["view"] == "hobby" and r["totals"] == {"income_micro": 2000000}
    assert set(r["months"][9]) == {"month", "income_micro", "bp"}
    with pytest.raises(ValueError):
        T.build_tax(make(), 2026, "x")


def test_unset_rates_give_no_net_and_voided_hardware_is_excluded():
    r = T.build_tax(make(rates=False), 2026, "business")
    assert r["months"][9]["net_micro"] is None and r["totals"]["net_micro"] is None and r["totals"]["income_micro"] == 2000000
    db = make()
    AE.void_entry(db, 1, 2)
    v = T.build_tax(db, 2026, "business")
    assert v["months"][9]["depreciation_business_micro"] is None and v["months"][9]["net_micro"] is None
