"""Frozen test: accounting settings can hold the machine records and the entry-to-machine links. Fake data."""
import sqlite3

import bloom_accounting_config as CF

MACHINES = [{"id": "box1", "display_name": "Box One", "processor": "Test CPU", "ownership": "owned", "in_service": "2026-03-01",
             "business_mode": "auto_paid_hours", "purchase_cents": 100000, "depreciation_method": "macrs5"}]


def test_new_keys_default_to_none_and_stay_unflagged():
    assert "machines" in CF.DEFAULTS and "entry_machine_links" in CF.DEFAULTS
    v = CF.effective_settings(sqlite3.connect(":memory:"), "2026-10-31")
    assert v["values"]["machines"] is None and v["values"]["entry_machine_links"] is None
    assert not [f for f in v["flags"] if f["key"] in ("machines", "entry_machine_links")]
    assert v["values"]["dep_method"] == "straight_line" and v["values"]["dep_life_months"] == 60


def test_machines_and_links_round_trip_with_effective_dates():
    db = sqlite3.connect(":memory:")
    CF.set_setting(db, "machines", MACHINES, "2026-03-01", 1)
    CF.set_setting(db, "entry_machine_links", {"7": "box1"}, "2026-03-01", 2)
    assert CF.effective_settings(db, "2026-02-28")["values"]["machines"] is None
    got = CF.effective_settings(db, "2026-03-01")["values"]
    assert got["machines"] == MACHINES and got["entry_machine_links"] == {"7": "box1"}
