"""Frozen test: the universal energy charge is a versioned setting; rate schedules are stored as dated JSON lists."""
import sqlite3

import bloom_accounting_config as C

SCHED = [{"months": [10, 11, 12, 1, 2, 3, 4, 5], "periods": [{"start": "00:00", "end": "24:00", "rate": "0.08415"}]}]


def test_key_defaults_none_and_flagged():
    assert C.DEFAULTS["universal_charge_usd_per_kwh"] is None
    assert C.FLAGGED["universal_charge_usd_per_kwh"].startswith("UNKNOWN")


def test_versioned_by_effective_date():
    db = sqlite3.connect(":memory:")
    C.create_settings_table(db)
    C.set_setting(db, "universal_charge_usd_per_kwh", "0.00039", "2026-10-01", 1)
    C.set_setting(db, "rate_schedule", SCHED, "2026-10-01", 2)
    assert C.effective_settings(db, "2026-09-30")["values"]["universal_charge_usd_per_kwh"] is None
    got = C.effective_settings(db, "2026-10-02")["values"]
    assert got["universal_charge_usd_per_kwh"] == "0.00039" and got["rate_schedule"] == SCHED
