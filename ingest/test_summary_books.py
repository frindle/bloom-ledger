"""Frozen test: the home summary Net uses the tax method (business share of power and lease, entries, receipts, pre-tracking pay)."""
import datetime as dt
import sqlite3

import bloom_accounting_config as CF
import bloom_accounting_depr as DP
import bloom_accounting_entries as AE
import bloom_accounting_index as AX
import bloom_accounting_summary as SM
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
    vals = {"rate_schedule": SCHED, "rate_adder_usd_per_kwh": "0", "universal_charge_usd_per_kwh": "0", "county_fee_pct": "0",
            "m4_machine_id": "m4", "m5_machine_id": "m5", "m4_in_service_date": "2026-10-01", "dep_life_months": 60,
            "m5_lease_monthly_cents": 10000, "m5_lease_months": 36, "m5_lease_start": "2026-10-01"}
    for k, v in vals.items():
        CF.set_setting(db, k, v, "2026-10-01", 1)
    AE.add_entry(db, {"kind": "cost", "date": "2026-08-13", "amount_cents": 182600, "category": "hardware", "machine_id": "m4"}, 1)
    AE.add_entry(db, {"kind": "cost", "date": "2026-10-05", "amount_cents": 1200, "category": "software", "machine_id": None}, 1)
    AE.add_entry(db, {"kind": "cost", "date": "2026-10-06", "amount_cents": 4000, "category": "internet", "machine_id": "m5"}, 1)
    AE.add_entry(db, {"kind": "cost", "date": "2026-10-06", "amount_cents": 9000, "category": "electricity", "machine_id": None}, 1)
    AE.add_entry(db, {"kind": "receipt", "date": "2026-10-07", "amount_cents": 500, "category": "other", "machine_id": None}, 1)
    return db


def test_net_matches_the_tax_method():
    s = SM.build(make(), "2026-10-31", "month")
    lease_biz, depr_biz = DP.business_cents(s["lease_cents"], 5000), DP.business_cents(s["depreciation_cents"], 5000)
    assert s["lease_business_cents"] == lease_biz and s["depreciation_business_cents"] == depr_biz
    assert s["power_business_micro"] == 100000 and s["pre_tracking_micro"] == 16515444 and s["receipts_micro"] == 5000000
    assert s["entries_business_micro"] == 1200 * 10000 + 2000 * 10000 and s["electricity_entries_micro"] == 90000000
    assert s["net_micro"] == 2000000 + 16515444 + 5000000 - 100000 - 32000000 - (lease_biz + depr_biz) * 10000
    t = T.build_tax(make(), 2026)["months"][9]
    assert s["net_micro"] == t["net_micro"]


def test_machine_view_skips_pre_tracking_and_other_machines_entries():
    s = SM.build(make(), "2026-10-31", "month", machine="m4")
    assert s["pre_tracking_micro"] == 0 and s["entries_business_micro"] == 1200 * 10000 and s["receipts_micro"] == 5000000
    assert s["lease_business_cents"] == 0
