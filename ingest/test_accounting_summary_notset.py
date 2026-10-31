"""Frozen test: not_set lists every missing electricity input, even for an empty period."""
import sqlite3

import bloom_accounting_config as CF
import bloom_accounting_index as AX
import bloom_accounting_summary as SM


def fresh():
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    return db


def test_empty_period_still_lists_missing_inputs():
    s = SM.build(fresh(), "2026-10-31", "month")
    assert s["not_set"] == ["rate_schedule", "rate_adder_usd_per_kwh", "universal_charge_usd_per_kwh", "county_fee_pct"]
    assert SM.RATE_KEYS[0] == "rate_schedule"


def test_set_inputs_drop_off_the_list():
    db = fresh()
    CF.set_setting(db, "rate_adder_usd_per_kwh", "0.00096", "2026-10-01", 1)
    CF.set_setting(db, "county_fee_pct", "5", "2026-10-01", 1)
    assert SM.build(db, "2026-10-31", "month")["not_set"] == ["rate_schedule", "universal_charge_usd_per_kwh"]
