"""Frozen test: bloom_accounting_depr.straight_line_cents."""
import datetime as dt

import bloom_accounting_depr as D

INS = "2026-10-01"


def test_daily_rate_and_exact_total_over_life():
    assert D.straight_line_cents(36500, 12, INS, INS, INS) == 100
    assert D.straight_line_cents(36500, 12, INS, "2026-10-01", "2026-10-31") == 3100
    end = (dt.date(2026, 10, 1) + dt.timedelta(days=364)).isoformat()
    assert D.straight_line_cents(36500, 12, INS, INS, end) == 36500
    assert D.straight_line_cents(36500, 12, INS, INS, "2040-01-01") == 36500


def test_before_in_service_and_after_life_are_zero():
    assert D.straight_line_cents(36500, 12, INS, "2026-01-01", "2026-09-30") == 0
    assert D.straight_line_cents(36500, 12, INS, "2028-01-01", "2028-12-31") == 0


def test_ranges_add_up_exactly_with_uneven_basis():
    basis = 322565
    whole = D.straight_line_cents(basis, 60, INS, "2026-10-01", "2027-12-31")
    parts = sum(D.straight_line_cents(basis, 60, INS, a, b) for a, b in
                (("2026-10-01", "2026-10-31"), ("2026-11-01", "2026-12-31"), ("2027-01-01", "2027-12-31")))
    assert whole == parts
    assert D.straight_line_cents(basis, 60, INS, INS, "2040-01-01") == basis
