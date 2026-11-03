"""Frozen test: bloom_accounting_report.totals."""
import bloom_accounting_report as RP


def row(d, e, tok, wh, mins, paid, cost):
    return {"date": d, "earned_micro": e, "tokens": tok, "wh": wh, "minutes": mins, "paid_minutes": paid, "cost_micro": cost}


def test_sums_and_derived_figures():
    t = RP.totals([row("2026-10-21", 100, 5, 1500.0, 90, 30, 10), row("2026-10-20", 50, 2, 500.0, 30, 0, 5)])
    assert (t["earned_micro"], t["tokens"], t["wh"], t["minutes"], t["paid_minutes"], t["cost_micro"]) == (150, 7, 2000.0, 120, 30, 15)
    assert t["kwh"] == 2.0 and t["total_hours"] == 2.0 and t["paid_hours"] == 0.5 and t["business_bp"] == 2500


def test_unset_cost_and_no_minutes():
    t = RP.totals([row("a", 1, 0, 0.0, 0, 0, None), row("b", 1, 0, 0.0, 0, 0, 5)])
    assert t["cost_micro"] is None and t["business_bp"] is None and t["earned_micro"] == 2
    assert RP.totals([]) == {"earned_micro": 0, "sandbox_micro": 0, "sandbox_cost_micro": 0, "sandbox_minutes": 0, "tokens": 0, "wh": 0.0, "minutes": 0, "paid_minutes": 0, "cost_micro": 0,
                             "kwh": 0.0, "total_hours": 0.0, "paid_hours": 0.0, "business_bp": None}
