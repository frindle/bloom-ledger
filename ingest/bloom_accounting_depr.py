"""Accounting depreciation in integer cents for a date range, using cumulative daily accrual so periods add up exactly.

Dates are YYYY-MM-DD strings, ranges inclusive. Not tax advice; the method is a setting."""
import datetime as dt


def _cum_sl(basis, life_months, in_service, day):
    days = (day - in_service).days + 1
    if days <= 0:
        return 0
    life_days = life_months * 36525 // 1200
    if days >= life_days:
        return basis
    return basis * days // life_days


def straight_line_cents(basis_cents, life_months, in_service, start, end):
    sd = dt.date.fromisoformat(start) - dt.timedelta(days=1)
    return _cum_sl(basis_cents, life_months, dt.date.fromisoformat(in_service), dt.date.fromisoformat(end)) - _cum_sl(basis_cents, life_months, dt.date.fromisoformat(in_service), sd)
