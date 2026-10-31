"""Frozen test: bloom_accounting_config.effective_settings."""
import bloom_accounting_config as C
import bloom_ingest as I


def mk(tmp_path):
    return I.open_db(tmp_path / "i.sqlite")


def test_defaults_when_nothing_set(tmp_path):
    r = C.effective_settings(mk(tmp_path), "2026-10-20")
    assert r["values"] == C.DEFAULTS
    assert [f["key"] for f in r["flags"]] == list(C.FLAGGED)
    assert r["flags"][0]["reason"] == C.FLAGGED[r["flags"][0]["key"]]


def test_effective_dating_and_newest_wins(tmp_path):
    db = mk(tmp_path)
    C.set_setting(db, "kwh_rate_cents", 10, "2026-10-01", 1)
    C.set_setting(db, "kwh_rate_cents", 15, "2027-01-01", 2)
    C.set_setting(db, "kwh_rate_cents", 11, "2026-10-01", 3)
    assert C.effective_settings(db, "2026-12-31")["values"]["kwh_rate_cents"] == 11
    assert C.effective_settings(db, "2027-01-01")["values"]["kwh_rate_cents"] == 15
    assert C.effective_settings(db, "2026-09-30")["values"]["kwh_rate_cents"] is None


def test_flags_clear_when_set_and_return_when_nulled(tmp_path):
    db = mk(tmp_path)
    C.set_setting(db, "nevada_fee_pct", 1.5, "2026-10-01", 1)
    C.set_setting(db, "m4_in_service_date", "2026-10-05", "2026-10-01", 2)
    keys = [f["key"] for f in C.effective_settings(db, "2026-10-20")["flags"]]
    assert "nevada_fee_pct" not in keys and "m4_in_service_date" not in keys and "kwh_rate_cents" in keys
    C.set_setting(db, "nevada_fee_pct", None, "2026-10-10", 3)
    assert "nevada_fee_pct" in [f["key"] for f in C.effective_settings(db, "2026-10-20")["flags"]]
