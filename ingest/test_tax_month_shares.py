"""Frozen test: bloom_accounting_tax.month_shares (monthly income, power cost and paid-minute share). Fake numbers."""
import bloom_accounting_tax as T


def row(date, earned, cost, minutes, paid):
    return {"date": date, "earned_micro": earned, "tokens": 1, "wh": 1.0, "minutes": minutes, "paid_minutes": paid, "cost_micro": cost}


ROWS = [row("2026-10-20", 3000000, 400000, 60, 15), row("2026-10-02", 1000000, 100000, 60, 45), row("2026-11-05", 500000, None, 10, 10),
        row("2025-10-05", 999, 999, 99, 99)]


def test_twelve_months_always_present_and_keyed():
    s = T.month_shares(2026, ROWS)
    assert list(s) == ["2026-%02d" % m for m in range(1, 13)]
    assert s["2026-01"] == {"income_micro": 0, "power_micro": 0, "minutes": 0, "paid_minutes": 0, "bp": None}


def test_month_sums_and_paid_share():
    s = T.month_shares(2026, ROWS)
    assert s["2026-10"] == {"income_micro": 4000000, "power_micro": 500000, "minutes": 120, "paid_minutes": 60, "bp": 5000}


def test_unset_power_cost_stays_none_and_other_years_are_ignored():
    s = T.month_shares(2026, ROWS)
    assert s["2026-11"]["power_micro"] is None and s["2026-11"]["income_micro"] == 500000 and s["2026-11"]["bp"] == 10000
    assert sum(v["income_micro"] for v in s.values()) == 4500000
    assert T.month_shares(2025, ROWS)["2025-10"]["income_micro"] == 999
