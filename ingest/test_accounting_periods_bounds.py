"""Frozen test: bloom_accounting_periods.period_bounds."""
import pytest

import bloom_accounting_periods as P


def test_day_week_month():
    assert P.period_bounds("2026-10-31", "day") == ("2026-10-31", "2026-10-31")
    assert P.period_bounds("2026-10-31", "week") == ("2026-10-26", "2026-11-01")
    assert P.period_bounds("2026-10-26", "week") == ("2026-10-26", "2026-11-01")
    assert P.period_bounds("2026-11-01", "week") == ("2026-10-26", "2026-11-01")
    assert P.period_bounds("2026-02-10", "month") == ("2026-02-01", "2026-02-28")
    assert P.period_bounds("2028-02-10", "month") == ("2028-02-01", "2028-02-29")
    assert P.period_bounds("2026-12-15", "month") == ("2026-12-01", "2026-12-31")


def test_quarter_and_year():
    assert P.period_bounds("2026-10-31", "quarter") == ("2026-10-01", "2026-12-31")
    assert P.period_bounds("2026-05-01", "quarter") == ("2026-04-01", "2026-06-30")
    assert P.period_bounds("2026-03-31", "quarter") == ("2026-01-01", "2026-03-31")
    assert P.period_bounds("2026-07-04", "year") == ("2026-01-01", "2026-12-31")


def test_unknown_period_raises():
    with pytest.raises(ValueError, match="unknown period: decade"):
        P.period_bounds("2026-10-31", "decade")
