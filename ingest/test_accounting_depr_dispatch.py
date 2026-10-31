"""Frozen test: bloom_accounting_depr.depreciation_cents / business_cents."""
import pytest

import bloom_accounting_depr as D

INS = "2026-10-01"


def test_dispatch_matches_the_underlying_methods():
    args = (100000, INS, 60, "2026-10-01", "2027-12-31")
    assert D.depreciation_cents("straight_line", *args) == D.straight_line_cents(100000, 60, INS, "2026-10-01", "2027-12-31")
    assert D.depreciation_cents("section179", *args) == 100000
    assert D.depreciation_cents("macrs5", *args) == D.macrs5_cents(100000, INS, "2026-10-01", "2027-12-31")


def test_unknown_method_raises():
    with pytest.raises(ValueError, match="unknown method: magic"):
        D.depreciation_cents("magic", 1, INS, 60, INS, INS)


def test_business_cents_floors_and_validates():
    assert D.business_cents(10000, 2500) == 2500
    assert D.business_cents(999, 3333) == 332
    assert D.business_cents(500, 0) == 0 and D.business_cents(500, 10000) == 500
    for bad in (-1, 10001, 50.0, True, "5"):
        with pytest.raises(ValueError, match="bad pct"):
            D.business_cents(100, bad)
