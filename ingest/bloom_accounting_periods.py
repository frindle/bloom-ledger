"""Accounting periods: calendar bounds for day, ISO week (Monday start), month, quarter and year, in UTC dates.

Dates are YYYY-MM-DD strings and ranges are inclusive. Not tax advice."""
import datetime as dt


PERIODS = ("day", "week", "month", "quarter", "year")


def _month_end(y, m):
    """Return the last date of month m in year y."""
    if m == 12:
        return dt.date(y + 1, 1, 1) - dt.timedelta(days=1)
    else:
        return dt.date(y, m + 1, 1) - dt.timedelta(days=1)


def period_bounds(date_str, period):
    d = dt.date.fromisoformat(date_str)
    if period not in PERIODS:
        raise ValueError(f"unknown period: {period}")
    if period == "day":
        return (date_str, date_str)
    elif period == "week":
        monday = d - dt.timedelta(days=d.weekday())
        sunday = monday + dt.timedelta(days=6)
        return (monday.isoformat(), sunday.isoformat())
    elif period == "month":
        end = _month_end(d.year, d.month)
        return (d.replace(day=1).isoformat(), end.isoformat())
    elif period == "quarter":
        q_start_month = ((d.month - 1) // 3) * 3 + 1
        q_start = d.replace(month=q_start_month, day=1)
        q_end_month = q_start_month + 2
        q_end = _month_end(d.year, q_end_month)
        return (q_start.isoformat(), q_end.isoformat())
    elif period == "year":
        return (f"{d.year}-01-01", f"{d.year}-12-31")
