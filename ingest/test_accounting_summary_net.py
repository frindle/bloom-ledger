"""Frozen test: summary lease, depreciation and net figures."""
import datetime as dt
import sqlite3

import bloom_accounting_config as CF
import bloom_accounting_depr as DP
import bloom_accounting_entries as AE
import bloom_accounting_index as AX
import bloom_accounting_summary as SM

SCHED = [{"months": list(range(1, 13)), "periods": [{"start": "00:00", "end": "24:00", "rate": "0.1"}]}]


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def make(lease=True, hardware=True):
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, completion_tokens, source_machine) VALUES ('e', ?, 2000000, 'job', 9, 'm4')",
               (utc(2026, 10, 20, 20, 0),))
    for m in (0, 1):
        db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, other_work, tokens_delta) VALUES ('m4', ?, 1000, 60, 1, 0, ?)",
                   (utc(2026, 10, 20, 20, m), 3 if m == 0 else 0))
    db.commit()
    vals = {"rate_schedule": SCHED, "rate_adder_usd_per_kwh": "0", "universal_charge_usd_per_kwh": "0", "county_fee_pct": "0",
            "m4_machine_id": "m4", "m5_machine_id": "m5", "m4_in_service_date": "2026-10-01", "dep_life_months": 60}
    if lease:
        vals.update({"m5_lease_monthly_cents": 10000, "m5_lease_months": 36, "m5_lease_start": "2026-10-01"})
    for k, v in vals.items():
        CF.set_setting(db, k, v, "2026-10-01", 1)
    if hardware:
        AE.add_entry(db, {"kind": "cost", "date": "2026-08-13", "amount_cents": 182600, "category": "hardware", "machine_id": "m4"}, 1)
    return db


def test_net_all_machines():
    s = SM.build(make(), "2026-10-31", "month")
    assert s["totals"]["business_bp"] == 5000
    assert s["lease_cents"] == 10000 * 12 * 31 // 365
    assert s["depreciation_cents"] == 182600 * 31 // 1826 and s["depreciation_business_cents"] == s["depreciation_cents"] // 2
    assert s["net_missing"] == []
    assert s["lease_business_cents"] == DP.business_cents(s["lease_cents"], 5000) and s["power_business_micro"] == 100000
    assert s["net_micro"] == 2000000 - 100000 - (s["lease_business_cents"] + s["depreciation_business_cents"]) * 10000


def test_missing_inputs_give_no_net():
    s = SM.build(make(lease=False, hardware=False), "2026-10-31", "month")
    assert s["net_micro"] is None and s["net_missing"] == ["lease", "depreciation"]
    assert s["lease_cents"] is None and s["depreciation_cents"] is None


def test_machine_filters_split_lease_and_depreciation():
    owned = SM.build(make(), "2026-10-31", "month", machine="m4")
    assert owned["lease_cents"] == 0 and owned["depreciation_cents"] == 182600 * 31 // 1826 and owned["net_micro"] is not None
    leased = SM.build(make(), "2026-10-31", "month", machine="m5")
    assert leased["depreciation_cents"] == 0 and leased["lease_cents"] == 10000 * 12 * 31 // 365
