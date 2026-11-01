"""Frozen test: bloom_accounting_depr.asset_business_cents (yearly business-use percent). All numbers are fake."""
import pytest

import bloom_accounting_depr as D

INS = "2026-03-01"


def asset(**kw):
    a = {"basis_cents": 100000, "placed_in_service": INS}
    a.update(kw)
    return a


def test_each_year_uses_its_own_percent():
    a = asset(business_use_bp={"2026": 5000, "2027": 8000})
    assert D.asset_business_cents(a, "2026-01-01", "2026-12-31") == 10000
    assert D.asset_business_cents(a, "2027-01-01", "2027-12-31") == 25600
    assert D.asset_business_cents(a, "2026-01-01", "2027-12-31") == 35600


def test_unlisted_year_is_all_business_unless_default_given():
    a = asset(business_use_bp={"2026": 5000})
    assert D.asset_business_cents(a, "2028-01-01", "2028-12-31") == 19200
    assert D.asset_business_cents(a, "2028-01-01", "2028-12-31", default_bp=2500) == 4800
    assert D.asset_business_cents(a, "2026-01-01", "2026-12-31", default_bp=2500) == 10000
    assert D.asset_business_cents(asset(), "2027-01-01", "2027-12-31") == 32000


def test_elections_are_reduced_by_the_percent_too():
    a = asset(section179_cents=30000, business_use_bp={"2026": 5000})
    assert D.asset_business_cents(a, "2026-01-01", "2026-12-31") == D.asset_depreciation_cents(a, "2026-01-01", "2026-12-31") // 2
    assert D.asset_business_cents(a, "2026-01-01", "2026-12-31") == 22000


def test_bad_percent_raises_value_error():
    with pytest.raises(ValueError):
        D.asset_business_cents(asset(business_use_bp={"2026": 10001}), "2026-01-01", "2026-12-31")
