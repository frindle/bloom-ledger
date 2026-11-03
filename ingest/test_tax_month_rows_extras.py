"""Frozen test: month_rows and tax_totals carry other income (receipts) and expensed entries. Fake numbers."""
import bloom_accounting_tax as T

SH = {"2026-10": {"income_micro": 9000000, "power_micro": 2000000, "minutes": 100, "paid_minutes": 50, "bp": 5000},
      "2026-11": {"income_micro": 1000000, "power_micro": 0, "minutes": 10, "paid_minutes": 10, "bp": 10000}}
FX = {k: {"depreciation_business_cents": 300, "lease_business_cents": 100} for k in SH}
def rows(*a):
    import inspect
    T.tax_totals(T.month_rows(*a[:3]))
    assert "extras" in inspect.signature(T.month_rows).parameters, "month_rows has no extras argument"
    return T.month_rows(*a)


EX = {"2026-10": {"other_income_micro": 1500000, "entries_business_micro": 700000}}


def test_entries_are_expenses_and_receipts_are_other_income():
    r = rows(2026, SH, FX, EX)
    assert r[0] == {"month": "2026-10", "income_micro": 9000000, "other_income_micro": 1500000, "bp": 5000, "power_business_micro": 1000000,
                    "depreciation_business_micro": 3000000, "lease_business_micro": 1000000, "entries_business_micro": 700000,
                    "expenses_micro": 5700000, "net_micro": 9000000 + 1500000 - 5700000}
    assert r[1]["other_income_micro"] == 0 and r[1]["entries_business_micro"] == 0 and r[1]["net_micro"] == 1000000 - 4000000


def test_no_extras_means_zero_and_totals_sum_new_columns():
    assert rows(2026, SH, FX) == rows(2026, SH, FX, {})
    t = T.tax_totals(rows(2026, SH, FX, EX))
    assert t["other_income_micro"] == 1500000 and t["entries_business_micro"] == 700000
    assert t["net_micro"] == 9000000 + 1500000 - 5700000 + 1000000 - 4000000
    assert "extras" in T.month_rows.__doc__ and "entries_business_micro" in T.tax_totals.__doc__
    assert list(t) == ["income_micro", "other_income_micro", "power_business_micro", "depreciation_business_micro", "lease_business_micro",
                       "entries_business_micro", "expenses_micro", "net_micro"]
