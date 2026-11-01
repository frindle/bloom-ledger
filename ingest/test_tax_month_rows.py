"""Frozen test: bloom_accounting_tax.month_rows (monthly business-view rows). Fake numbers."""
import bloom_accounting_tax as T


def sh(income, power, bp):
    return {"income_micro": income, "power_micro": power, "minutes": 100, "paid_minutes": 50, "bp": bp}


SHARES = {"2026-10": sh(9000000, 2000000, 5000), "2026-11": sh(4000000, None, 10000), "2026-12": sh(0, 0, None)}
FIXED = {"2026-10": {"depreciation_business_cents": 300, "lease_business_cents": 100},
         "2026-11": {"depreciation_business_cents": 0, "lease_business_cents": 0},
         "2026-12": {"depreciation_business_cents": None, "lease_business_cents": 0}}


def test_expenses_are_power_at_share_plus_fixed_and_net_follows():
    r = T.month_rows(2026, SHARES, FIXED)
    assert [x["month"] for x in r] == ["2026-10", "2026-11", "2026-12"]
    assert r[0] == {"month": "2026-10", "income_micro": 9000000, "bp": 5000, "power_business_micro": 1000000,
                    "depreciation_business_micro": 3000000, "lease_business_micro": 1000000, "expenses_micro": 5000000, "net_micro": 4000000}


def test_unset_inputs_propagate_none_to_expenses_and_net():
    r = T.month_rows(2026, SHARES, FIXED)
    assert r[1]["power_business_micro"] is None and r[1]["expenses_micro"] is None and r[1]["net_micro"] is None and r[1]["income_micro"] == 4000000
    assert r[2]["depreciation_business_micro"] is None and r[2]["lease_business_micro"] == 0 and r[2]["net_micro"] is None
    assert r[2]["power_business_micro"] == 0


def test_missing_fixed_month_counts_as_unset():
    r = T.month_rows(2026, {"2026-10": sh(1000000, 0, 5000)}, {})
    assert r[0]["depreciation_business_micro"] is None and r[0]["net_micro"] is None
