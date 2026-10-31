"""Accounting periods: calendar bounds for day, ISO week (Monday start), month, quarter and year, in UTC dates.

Dates are YYYY-MM-DD strings and ranges are inclusive. Not tax advice."""
import datetime as dt


PERIODS = ("day", "week", "month", "quarter", "year")


def _month_end(y, m):
    return dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)


def period_bounds(date_str, period):
    """(start, end) ISO date strings of the `period` containing `date_str`; ValueError for an unknown period."""
    d = dt.date.fromisoformat(date_str)
    if period == "day":
        s, e = d, d
    elif period == "week":
        s = d - dt.timedelta(days=d.weekday())
        e = s + dt.timedelta(days=6)
    elif period == "month":
        s, e = d.replace(day=1), _month_end(d.year, d.month)
    elif period == "quarter":
        q = 3 * ((d.month - 1) // 3) + 1
        s, e = dt.date(d.year, q, 1), _month_end(d.year, q + 2)
    elif period == "year":
        s, e = dt.date(d.year, 1, 1), dt.date(d.year, 12, 31)
    else:
        raise ValueError("unknown period: %s" % period)
    return s.isoformat(), e.isoformat()


def report_range(name, today):
    if name == "day":
        return period_bounds(today, "day")
    elif name == "week":
        return period_bounds(today, "week")
    elif name == "month":
        return period_bounds(today, "month")
    elif name == "quarter":
        return period_bounds(today, "quarter")
    elif name == "ytd":
        d = dt.date.fromisoformat(today)
        start = dt.date(d.year, 1, 1).isoformat()
        return start, today
    elif name == "last_year":
        prev = dt.date.fromisoformat(today).year - 1
        return dt.date(prev, 1, 1).isoformat(), dt.date(prev, 12, 31).isoformat()
    else:
        raise ValueError("unknown report period: %s" % name)


def bucket_key(date_str, period):
    d = dt.date.fromisoformat(date_str)
    if period == "day":
        return date_str
    elif period == "week":
        iso = d.isocalendar()
        return "%d-W%02d" % (iso[0], iso[1])
    elif period == "month":
        return "%04d-%02d" % (d.year, d.month)
    elif period == "quarter":
        q = 3 * ((d.month - 1) // 3) + 1
        return "%d-Q%d" % (d.year, (q - 1) // 3 + 1)
    elif period == "year":
        return "%d" % d.year
    else:
        raise ValueError("unknown period: %s" % period)
