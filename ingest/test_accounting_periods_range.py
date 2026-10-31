"""Frozen test: bloom_accounting_periods.report_range / bucket_key."""
import pytest

import bloom_accounting_periods as P


def test_report_range_names():
    t = "2026-10-31"
    assert P.report_range("day", t) == ("2026-10-31", "2026-10-31")
    assert P.report_range("week", t) == ("2026-10-26", "2026-11-01")
    assert P.report_range("month", t) == ("2026-10-01", "2026-10-31")
    assert P.report_range("quarter", t) == ("2026-10-01", "2026-12-31")
    assert P.report_range("ytd", t) == ("2026-01-01", "2026-10-31")
    assert P.report_range("last_year", t) == ("2025-01-01", "2025-12-31")
    with pytest.raises(ValueError, match="unknown report period: year"):
        P.report_range("year", t)


def test_bucket_keys():
    assert P.bucket_key("2026-10-31", "day") == "2026-10-31"
    assert P.bucket_key("2026-10-31", "week") == "2026-W44"
    assert P.bucket_key("2026-01-01", "week") == "2026-W01"
    assert P.bucket_key("2027-01-01", "week") == "2026-W53"
    assert P.bucket_key("2026-10-31", "month") == "2026-10"
    assert P.bucket_key("2026-10-31", "quarter") == "2026-Q4"
    assert P.bucket_key("2026-03-31", "quarter") == "2026-Q1"
    assert P.bucket_key("2026-10-31", "year") == "2026"
    with pytest.raises(ValueError, match="unknown period"):
        P.bucket_key("2026-10-31", "hour")
