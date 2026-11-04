"""Frozen test: bloom_accounting_depr.asset_depreciation_cents (asset records with elections). All numbers are fake."""
import pytest

import bloom_accounting_depr as D

INS = "2026-03-01"


def asset(**kw):
    a = {"basis_cents": 100000, "placed_in_service": INS}
    a.update(kw)
    return a


def test_default_asset_is_five_year_macrs():
    a = asset()
    assert D.asset_depreciation_cents(a, "2026-01-01", "2026-12-31") == 20000
    assert D.asset_depreciation_cents(a, "2027-01-01", "2027-12-31") == 32000
    assert D.asset_depreciation_cents(a, "2026-01-01", "2040-12-31") == 100000


def test_old_straight_line_record_still_works():
    a = asset(method="straight_line", life_months=60, basis_cents=120000)
    want = D.straight_line_cents(120000, 60, INS, "2026-03-01", "2026-12-31")
    assert want > 0 and D.asset_depreciation_cents(a, "2026-03-01", "2026-12-31") == want
    assert D.asset_depreciation_cents(a, "2026-01-01", "2040-12-31") == 120000


def test_section179_election_is_expensed_on_the_in_service_day():
    a = asset(section179_cents=30000)
    assert D.asset_depreciation_cents(a, "2026-03-01", "2026-03-01") == 30000 + D.macrs5_cents(70000, INS, "2026-03-01", "2026-03-01")
    assert D.asset_depreciation_cents(a, "2027-01-01", "2027-12-31") == 22400
    assert D.asset_depreciation_cents(a, "2026-01-01", "2040-12-31") == 100000
    assert D.asset_depreciation_cents(asset(section179_cents=999999), "2026-03-01", "2026-03-01") == 100000
    whole = asset(method="section179")
    assert D.asset_depreciation_cents(whole, "2026-01-01", "2026-12-31") == 100000
    assert D.asset_depreciation_cents(whole, "2027-01-01", "2027-12-31") == 0


def test_bonus_applies_to_what_section179_left():
    a = asset(section179_cents=20000, bonus_bp=5000)
    assert D.asset_depreciation_cents(a, "2026-03-01", "2026-03-01") >= 60000
    assert D.asset_depreciation_cents(a, "2027-01-01", "2027-12-31") == 12800
    assert D.asset_depreciation_cents(a, "2026-01-01", "2040-12-31") == 100000


def test_bad_records_raise_value_error():
    for bad in (asset(method="bogus"), asset(convention="monthly"), asset(**{"class": "40-year"}), asset(bonus_bp=10001)):
        with pytest.raises(ValueError):
            D.asset_depreciation_cents(bad, "2026-01-01", "2026-12-31")
