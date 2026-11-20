"""Frozen test: the unset defaults are the Darkbloom start date and 5-year MACRS, both flagged for the accountant. Fake data."""
import sqlite3

import bloom_accounting_config as CF


def flags_and_values():
    v = CF.effective_settings(sqlite3.connect(":memory:"), "2026-10-31")
    return {f["key"]: str(f) for f in v["flags"]}, v["values"]


def test_in_service_default():
    flags, values = flags_and_values()
    assert values["m4_in_service_date"] is None
    assert "m4_in_service_date" in flags and "UNKNOWN" in flags["m4_in_service_date"], flags.get("m4_in_service_date")


def test_env_defaults(monkeypatch):
    monkeypatch.delenv("TZ", raising=False)
    for k in ("BLOOM_TIMEZONE", "LOCAL_TIMEZONE", "BLOOM_INGEST_FROM", "BLOOM_IN_SERVICE_DATE", "BLOOM_M4_IN_SERVICE_DATE"):
        monkeypatch.delenv(k, raising=False)
    d = CF.live_defaults()
    assert d["local_timezone"] == "UTC" and d["ingest_from"] is None and d["m4_in_service_date"] is None
    monkeypatch.setenv("BLOOM_TIMEZONE", "America/Los_Angeles")
    monkeypatch.setenv("BLOOM_M4_IN_SERVICE_DATE", "2026-09-28")  # old-style name still accepted
    monkeypatch.setenv("BLOOM_INGEST_FROM", "2026-10-13")
    d = CF.live_defaults()
    assert (d["local_timezone"], d["m4_in_service_date"], d["ingest_from"]) == ("America/Los_Angeles", "2026-09-28", "2026-10-13")
    monkeypatch.setenv("BLOOM_TIMEZONE", "Not/AZone")
    assert CF.default_timezone() == "UTC"  # a bad zone never crashes the server


def test_ingest_from_ts_env(monkeypatch):
    import bloom_accounting_index as AX
    monkeypatch.delenv("INGEST_FROM_TS", raising=False)
    monkeypatch.delenv("BLOOM_INGEST_FROM", raising=False)
    assert AX.ingest_from_ts() == 0
    monkeypatch.setenv("INGEST_FROM_TS", "1791849600")
    assert AX.ingest_from_ts() == 1791849600
    monkeypatch.delenv("INGEST_FROM_TS")
    monkeypatch.setenv("BLOOM_INGEST_FROM", "2026-10-13")
    assert AX.ingest_from_ts() == 1791849600
    monkeypatch.setenv("BLOOM_INGEST_FROM", "junk")
    assert AX.ingest_from_ts() == 0


def test_dep_method_default():
    flags, values = flags_and_values()
    assert CF.DEFAULTS["dep_method"] == "macrs5", CF.DEFAULTS["dep_method"]
    assert values["dep_method"] == "macrs5"
    assert "dep_method" in flags and "DEFAULT macrs5 (5-year MACRS, half-year convention)" in flags["dep_method"], flags.get("dep_method")
    db = sqlite3.connect(":memory:")
    CF.set_setting(db, "dep_method", "straight_line", "2026-01-01", 1)
    assert CF.effective_settings(db, "2026-10-31")["values"]["dep_method"] == "straight_line"
    assert "dep_method" not in {f["key"] for f in CF.effective_settings(db, "2026-10-31")["flags"]}
