"""Earnings over time for the home page graph: GET /v1/earnings/series.

Daily earnings (UTC days, the same day Darkbloom accounts by, zero-filled between the first and the last day so the chart has no
holes), each day's running total, and a month roll-up with its own running total. Money is integer micro-USD. The shaping is
pure (shape) so it is tested without a database. Bookkeeping view, not tax advice."""
import datetime as dt
import json
import urllib.parse
from zoneinfo import ZoneInfo

import bloom_accounting_config as CF

KINDS = ("job", "sandbox", "base")


def shape(rows, tz, today=None):
    """rows: iterable of (epoch_ts, micro_usd, kind). Returns {"timezone", "days", "months", "total_micro"}.
    days: {date, earned_micro, inference_micro, sandbox_micro, base_micro, cumulative_micro}, oldest first, zero-filled up to
    `today` (a YYYY-MM-DD, default none: up to the last day with pay). months: {month, earned_micro, inference_micro, sandbox_micro, base_micro, days, cumulative_micro}."""
    zone = ZoneInfo(tz)
    per = {}
    for ts, micro, kind in rows:
        d = dt.datetime.fromtimestamp(ts, zone).date()
        r = per.setdefault(d, {"inference_micro": 0, "sandbox_micro": 0, "base_micro": 0})
        r[{"sandbox": "sandbox_micro", "base": "base_micro"}.get(kind, "inference_micro")] += micro
    if not per:
        return {"timezone": tz, "days": [], "months": [], "total_micro": 0}
    first, last = min(per), max(per)
    if today and dt.date.fromisoformat(today) > last:
        last = dt.date.fromisoformat(today)
    days, months, run = [], {}, 0
    d = first
    while d <= last:
        r = per.get(d, {"inference_micro": 0, "sandbox_micro": 0, "base_micro": 0})
        earned = r["inference_micro"] + r["sandbox_micro"] + r["base_micro"]
        run += earned
        days.append({"date": d.isoformat(), "earned_micro": earned, **r, "cumulative_micro": run})
        m = months.setdefault(d.strftime("%Y-%m"), {"month": d.strftime("%Y-%m"), "earned_micro": 0, "days": 0,
                                                                  "inference_micro": 0, "sandbox_micro": 0, "base_micro": 0})
        m["earned_micro"] += earned
        for k in ("inference_micro", "sandbox_micro", "base_micro"):
            m[k] += r[k]
        m["days"] += 1
        d += dt.timedelta(days=1)
    total = 0
    for m in months.values():
        total += m["earned_micro"]
        m["cumulative_micro"] = total
    return {"timezone": tz, "days": days, "months": list(months.values()), "total_micro": run}


def build(db, today=None):
    """The series for every earnings row in the ledger."""
    tz = CF.ACCOUNTING_TZ
    today = today or CF.utc_today()
    rows = db.execute("SELECT ts, micro_usd, kind FROM earnings ORDER BY ts").fetchall()
    return shape(rows, tz, today)


def series_response(db, path, today=None):
    """(status, content_type, body) for GET /v1/earnings/series (no query allowed)."""
    parts = urllib.parse.urlsplit(path)
    if parts.path != "/v1/earnings/series":
        return (404, "application/json", b'{"error": "not found"}')
    if parts.query:
        return (400, "application/json", b'{"error": "bad request"}')
    return (200, "application/json", json.dumps(build(db, today), sort_keys=True).encode())
