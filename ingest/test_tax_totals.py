"""Frozen test: bloom_accounting_tax.tax_totals. Fake numbers."""
import bloom_accounting_tax as T


def r(inc, pw, dep, lease):
    exp = None if None in (pw, dep, lease) else pw + dep + lease
    return {"month": "m", "income_micro": inc, "bp": 1, "power_business_micro": pw, "depreciation_business_micro": dep,
            "lease_business_micro": lease, "expenses_micro": exp, "net_micro": None if exp is None else inc - exp}


def test_sums_every_column():
    t = T.tax_totals([r(1000, 100, 200, 300), r(2000, 10, 20, 30)])
    assert t == {"income_micro": 3000, "power_business_micro": 110, "depreciation_business_micro": 220, "lease_business_micro": 330,
                 "expenses_micro": 660, "net_micro": 2340}


def test_none_in_any_month_makes_that_column_none_only():
    t = T.tax_totals([r(1000, 100, 200, 300), r(2000, None, 20, 30)])
    assert t["power_business_micro"] is None and t["expenses_micro"] is None and t["net_micro"] is None
    assert t["income_micro"] == 3000 and t["depreciation_business_micro"] == 220 and t["lease_business_micro"] == 330


def test_no_rows_is_all_zero():
    assert set(T.tax_totals([]).values()) == {0}
