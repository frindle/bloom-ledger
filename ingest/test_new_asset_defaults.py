"""Frozen test: bloom_accounting_depr.new_asset_defaults (5-year MACRS is the default for new assets)."""
import bloom_accounting_depr as D


def test_defaults_are_five_year_macrs_without_elections():
    d = D.new_asset_defaults()
    assert d["method"] == "macrs5" and d["class"] == "5-year" and d["convention"] == "half_year"
    assert d["section179_cents"] == 0 and d["bonus_bp"] == 0 and d["business_use_bp"] == {}
    assert d["life_months"] == 60


def test_cpa_flag_is_visible_text():
    assert D.new_asset_defaults()["cpa_flag"] == "confirm with CPA"


def test_each_call_returns_a_fresh_dict():
    a = D.new_asset_defaults()
    a["business_use_bp"]["2026"] = 5000
    a["method"] = "straight_line"
    b = D.new_asset_defaults()
    assert b["business_use_bp"] == {} and b["method"] == "macrs5"


def test_defaults_make_a_working_asset():
    a = dict(D.new_asset_defaults(), basis_cents=100000, placed_in_service="2026-03-01")
    assert D.asset_depreciation_cents(a, "2026-01-01", "2026-12-31") == 20000
    assert D.asset_business_cents(a, "2026-01-01", "2026-12-31") == 20000
