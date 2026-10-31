"""Frozen test: settings defaults carry the electricity rate schedule; the invented Nevada fee is gone."""
import bloom_accounting_config as C
import bloom_ingest as I


def test_removed_and_new_keys():
    assert "nevada_fee_pct" not in C.DEFAULTS and "kwh_rate_cents" not in C.DEFAULTS
    assert "nevada_fee_pct" not in C.FLAGGED and "kwh_rate_cents" not in C.FLAGGED
    assert C.DEFAULTS["rate_offpeak_usd_per_kwh"] == 0.07811
    assert C.DEFAULTS["rate_summer_onpeak_usd_per_kwh"] == 0.11712
    assert C.DEFAULTS["rate_summer_months"] == [6, 7, 8, 9]
    assert C.DEFAULTS["rate_onpeak_window"] == ["18:01", "21:00"]
    assert C.DEFAULTS["rate_adder_usd_per_kwh"] == 0.003 and C.DEFAULTS["county_fee_pct"] == 5
    assert C.DEFAULTS["m5_business_mode"] == "leased_100" and C.DEFAULTS["m4_business_mode"] == "auto_paid_hours"


def test_every_flag_is_a_known_key_and_assumptions_are_flagged():
    assert set(C.FLAGGED) <= set(C.DEFAULTS)
    for k in ("rate_adder_usd_per_kwh", "county_fee_pct", "m5_lease_monthly_cents"):
        assert k in C.FLAGGED


def test_rates_are_editable_and_effective_dated(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    C.set_setting(db, "rate_offpeak_usd_per_kwh", 0.09, "2027-01-01", 1)
    assert C.effective_settings(db, "2026-12-31")["values"]["rate_offpeak_usd_per_kwh"] == 0.07811
    assert C.effective_settings(db, "2027-01-01")["values"]["rate_offpeak_usd_per_kwh"] == 0.09
