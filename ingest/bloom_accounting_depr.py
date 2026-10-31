"""Accounting depreciation in integer cents for a date range, using cumulative daily accrual so periods add up exactly.

Dates are YYYY-MM-DD strings, ranges inclusive. Not tax advice; the method is a setting."""
import datetime as dt


def _cum_sl(basis, life_months, in_service, day):
    days = (day - in_service).days + 1
    if days <= 0:
        return 0
    life_days = life_months * 36525 // 1200
    return basis if days >= life_days else basis * days // life_days


def straight_line_cents(basis_cents, life_months, in_service, start, end):
    """Straight-line depreciation (cents) for the inclusive range start..end, accruing daily from in_service."""
    a, s, e = (dt.date.fromisoformat(x) for x in (in_service, start, end))
    return _cum_sl(basis_cents, life_months, a, e) - _cum_sl(basis_cents, life_months, a, s - dt.timedelta(days=1))


MACRS5_BP = (2000, 3200, 1920, 1152, 1152)


def section179_cents(basis_cents, in_service, start, end):
    return basis_cents if start <= in_service <= end else 0


def macrs5_year_amounts(basis_cents):
    first = [basis_cents * bp // 10000 for bp in MACRS5_BP]
    return first + [basis_cents - sum(first)]
