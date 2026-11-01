"""Frozen test: bloom_accounting_tax.apply_view (business vs hobby). Fake numbers."""
import pytest

import bloom_accounting_tax as T

MONTH = {"month": "2026-10", "income_micro": 900, "bp": 5000, "power_business_micro": 1, "depreciation_business_micro": 2,
         "lease_business_micro": 3, "expenses_micro": 6, "net_micro": 894}
REPORT = {"year": 2026, "view": "business", "months": [MONTH], "totals": {"income_micro": 900, "expenses_micro": 6, "net_micro": 894},
          "disclaimer": "Bookkeeping, not tax advice"}


def test_hobby_keeps_income_only_and_does_not_mutate():
    h = T.apply_view(REPORT, "hobby")
    assert h["view"] == "hobby" and h["months"] == [{"month": "2026-10", "income_micro": 900, "bp": 5000}]
    assert h["totals"] == {"income_micro": 900} and h["year"] == 2026 and h["disclaimer"] == "Bookkeeping, not tax advice"
    assert REPORT["months"][0] == MONTH and "expenses_micro" in REPORT["totals"]


def test_business_is_unchanged_and_bad_view_raises():
    b = T.apply_view(REPORT, "business")
    assert b == REPORT and b is not REPORT
    with pytest.raises(ValueError):
        T.apply_view(REPORT, "other")
