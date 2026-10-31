"""Frozen test: settings defaults carry the electricity rate schedule; the invented Nevada fee is gone."""
import bloom_accounting_config as C
import bloom_ingest as I


def test_removed_and_new_keys():
    assert "nevada_fee_pct" not in C.DEFAULTS and "kwh_rate_cents" not in C.DEFAULTS
    assert "nevada_fee_pct" not in C.FLAGGED and "kwh_rate_cents" not in C.FLAGGED
    for k in ("rate_schedule", "rate_adder_usd_per_kwh", "county_fee_pct"):
        assert C.DEFAULTS[k] is None, "no rate numbers are assumed"
    assert C.DEFAULTS["m5_business_mode"] == "leased_100" and C.DEFAULTS["m4_business_mode"] == "auto_paid_hours"


def test_every_flag_is_a_known_key_and_assumptions_are_flagged():
    assert set(C.FLAGGED) <= set(C.DEFAULTS)
    for k in ("rate_schedule", "rate_adder_usd_per_kwh", "county_fee_pct", "m5_lease_monthly_cents"):
        assert k in C.FLAGGED




def test_rate_schedule_is_user_entered_and_effective_dated(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    sched = {"offpeak": 0.1}
    C.set_setting(db, "rate_schedule", sched, "2027-01-01", 1)
    assert C.effective_settings(db, "2026-12-31")["values"]["rate_schedule"] is None
    assert C.effective_settings(db, "2027-01-01")["values"]["rate_schedule"] == sched
    assert "rate_schedule" not in [f["key"] for f in C.effective_settings(db, "2027-01-02")["flags"]]
