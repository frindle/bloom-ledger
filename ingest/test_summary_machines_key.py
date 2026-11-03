"""Frozen test: SM.build adds a per-machine "machines" list and leaves the pooled figures alone. Fake numbers."""
import datetime as dt
import sqlite3

import bloom_accounting_config as CF
import bloom_accounting_entries as AE
import bloom_accounting_index as AX
import bloom_accounting_summary as SM

SCHED = [{"months": list(range(1, 13)), "periods": [{"start": "00:00", "end": "24:00", "rate": "0.1"}]}]
OWNED = {"id": "m4", "display_name": "Box One", "ownership": "owned", "in_service": "2026-03-01",
         "depreciation_method": "macrs5", "purchase_cents": 100000}


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def make(machines=None):
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, completion_tokens, source_machine) VALUES ('e', ?, 2000000, 'job', 9, 'm4')",
               (utc(2026, 10, 20, 20, 0),))
    for m in (0, 1):
        db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, other_work, tokens_delta) VALUES ('m4', ?, 1000, 60, 1, 0, ?)",
                   (utc(2026, 10, 20, 20, m), 3 if m == 0 else 0))
    db.commit()
    vals = {"rate_schedule": SCHED, "rate_adder_usd_per_kwh": "0", "universal_charge_usd_per_kwh": "0", "county_fee_pct": "0",
            "m4_machine_id": "m4", "m5_machine_id": "m5", "m4_in_service_date": "2026-10-01", "dep_life_months": 60, "dep_method": "straight_line",
            "m5_lease_monthly_cents": 10000, "m5_lease_months": 36, "m5_lease_start": "2026-10-01"}
    if machines is not None:
        vals["machines"] = machines
    for k, v in vals.items():
        CF.set_setting(db, k, v, "2026-10-01", 1)
    AE.add_entry(db, {"kind": "cost", "date": "2026-08-13", "amount_cents": 50000, "category": "hardware", "machine_id": "m4"}, 1)
    return db


def test_no_machines_configured_gives_empty_list_and_same_pooled_figures():
    s = SM.build(make(), "2026-10-31", "month")
    assert s["machines"] == []
    assert s["lease_cents"] == 10000 * 12 * 31 // 365
    assert s["depreciation_cents"] == 50000 * 31 // 1826 and s["net_missing"] == []


def test_configured_machines_are_listed_for_the_period():
    s = SM.build(make([OWNED]), "2026-10-31", "month")
    assert [m["id"] for m in s["machines"]] == ["m4"]
    row = s["machines"][0]
    assert row["ownership"] == "owned" and row["lease_cents"] == 0
    want = SM.machine_breakdown({"machines": [OWNED]}, AE.current_entries(make()), "2026-10-01", "2026-10-31")[0]["depreciation_cents"]
    assert row["depreciation_cents"] == want and want > 0
    assert s["depreciation_cents"] == 50000 * 31 // 1826
