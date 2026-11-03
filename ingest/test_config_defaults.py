"""Frozen test: the unset defaults are the Darkbloom start date and 5-year MACRS, both flagged for the accountant. Fake data."""
import sqlite3

import bloom_accounting_config as CF


def flags_and_values():
    v = CF.effective_settings(sqlite3.connect(":memory:"), "2026-10-31")
    return {f["key"]: str(f) for f in v["flags"]}, v["values"]


def test_in_service_default():
    flags, values = flags_and_values()
    assert CF.DEFAULTS["m4_in_service_date"] == "2026-09-28", CF.DEFAULTS["m4_in_service_date"]
    assert values["m4_in_service_date"] == "2026-09-28"
    assert "m4_in_service_date" in flags and "ASSUMED 2026-09-28 (Darkbloom start)" in flags["m4_in_service_date"], flags.get("m4_in_service_date")


def test_dep_method_default():
    flags, values = flags_and_values()
    assert CF.DEFAULTS["dep_method"] == "macrs5", CF.DEFAULTS["dep_method"]
    assert values["dep_method"] == "macrs5"
    assert "dep_method" in flags and "DEFAULT macrs5 (5-year MACRS, half-year convention)" in flags["dep_method"], flags.get("dep_method")
    db = sqlite3.connect(":memory:")
    CF.set_setting(db, "dep_method", "straight_line", "2026-01-01", 1)
    assert CF.effective_settings(db, "2026-10-31")["values"]["dep_method"] == "straight_line"
    assert "dep_method" not in {f["key"] for f in CF.effective_settings(db, "2026-10-31")["flags"]}
