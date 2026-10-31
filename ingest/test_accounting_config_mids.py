"""Frozen test: the owned and leased machine ids are settings (default unset)."""
import sqlite3

import bloom_accounting_config as C


def test_defaults_unset():
    assert C.DEFAULTS["m4_machine_id"] is None and C.DEFAULTS["m5_machine_id"] is None


def test_can_be_set_and_read_back():
    db = sqlite3.connect(":memory:")
    C.set_setting(db, "m4_machine_id", "mac-studio-m4", "2026-10-01", 1)
    C.set_setting(db, "m5_machine_id", "mac-m5", "2026-10-01", 2)
    v = C.effective_settings(db, "2026-10-31")["values"]
    assert v["m4_machine_id"] == "mac-studio-m4" and v["m5_machine_id"] == "mac-m5"
