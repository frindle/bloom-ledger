"""Fixed machine costs in integer cents for a date range: lease expense and depreciation.

Accrual is cumulative by day so periods add up exactly. Bookkeeping estimates, not tax advice."""
import datetime as dt


def _cum_lease(monthly, months, start, day):
    days = (day - start).days + 1
    if days <= 0:
        return 0
    return min(monthly * months, monthly * 12 * days // 365)


def lease_cents(settings, start, end):
    monthly = settings.get("m5_lease_monthly_cents")
    months = settings.get("m5_lease_months")
    lease_start_str = settings.get("m5_lease_start")
    if monthly is None or months is None or lease_start_str is None:
        return None
    lease_start = dt.date.fromisoformat(lease_start_str)
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end)
    return _cum_lease(monthly, months, lease_start, e) - _cum_lease(monthly, months, lease_start, s - dt.timedelta(days=1))
