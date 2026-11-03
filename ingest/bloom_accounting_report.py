"""Accounting report rows: per local day earnings and tokens from the indexed earnings table.

Days are local dates (settings local_timezone); money is integer micro-USD. Bookkeeping estimates, not tax advice."""
import datetime as dt
from zoneinfo import ZoneInfo

import bloom_accounting_rates as RT


def ts_bounds(tz, start, end):
    """(first_ts, end_ts) UTC epoch seconds covering local dates start..end inclusive (end_ts is exclusive)."""
    zone = ZoneInfo(tz)
    s = dt.datetime.combine(dt.date.fromisoformat(start), dt.time(), zone)
    e = dt.datetime.combine(dt.date.fromisoformat(end) + dt.timedelta(days=1), dt.time(), zone)
    return int(s.timestamp()), int(e.timestamp())


def day_rows(db, tz, start, end, machine=None, settings=None):
    """Per local day {"date", "earned_micro", "tokens"} for days that have earnings, newest first.

    `machine` (optional) limits to earnings whose source_machine matches."""
    lo, hi = ts_bounds(tz, start, end)
    sql = "SELECT ts, micro_usd, completion_tokens, kind FROM earnings WHERE ts >= ? AND ts < ?"
    args = [lo, hi]
    if machine:
        sql += " AND source_machine = ?"
        args.append(machine)
    days = {}
    zone = ZoneInfo(tz)

    def row_for(d):
        return days.setdefault(d, {"date": d, "earned_micro": 0, "sandbox_micro": 0, "tokens": 0, "wh": 0.0, "minutes": 0, "paid_minutes": 0,
                                  "cost_micro": 0 if settings else None})
    for ts, micro, tokens, kind in db.execute(sql, args):
        d = dt.datetime.fromtimestamp(ts, zone).date().isoformat()
        row = row_for(d)
        row["earned_micro"] += micro
        if kind == "sandbox":
            row["sandbox_micro"] += micro
        row["tokens"] += tokens or 0
    psql = "SELECT ts, wh, power_ok, tokens_delta, other_work, sandbox_jobs FROM power_minutes WHERE ts >= ? AND ts < ?"
    pargs = [lo, hi]
    if machine:
        psql += " AND machine_id = ?"
        pargs.append(machine)
    for ts, wh, ok, tok, other, sbx in db.execute(psql, pargs):
        row = row_for(dt.datetime.fromtimestamp(ts, zone).date().isoformat())
        if ok:
            row["wh"] += wh or 0.0
            row["minutes"] += 1
            if settings and row["cost_micro"] is not None:
                c = RT.interval_cost(settings, ts, wh or 0.0)
                row["cost_micro"] = None if c is None else row["cost_micro"] + c["total_micro"]
            if ((tok or 0) > 0 or (sbx or 0) > 0) and not other:
                row["paid_minutes"] += 1
    return [days[d] for d in sorted(days, reverse=True)]


def totals(rows):
    """Aggregate day_rows into period figures."""
    earned_micro = 0
    sandbox_micro = 0
    tokens = 0
    wh = 0.0
    minutes = 0
    paid_minutes = 0
    cost_micro = 0
    cost_none = False
    for r in rows:
        earned_micro += r["earned_micro"]
        sandbox_micro += r.get("sandbox_micro", 0)
        tokens += r["tokens"]
        wh += r["wh"]
        minutes += r["minutes"]
        paid_minutes += r["paid_minutes"]
        c = r["cost_micro"]
        if c is None:
            cost_none = True
        else:
            cost_micro += c
    if cost_none:
        cost_micro = None
    kwh = round(wh / 1000, 3)
    total_hours = round(minutes / 60, 2)
    paid_hours = round(paid_minutes / 60, 2)
    business_bp = None if minutes == 0 else paid_minutes * 10000 // minutes
    return {
        "earned_micro": earned_micro,
        "sandbox_micro": sandbox_micro,
        "tokens": tokens,
        "wh": wh,
        "minutes": minutes,
        "paid_minutes": paid_minutes,
        "cost_micro": cost_micro,
        "kwh": kwh,
        "total_hours": total_hours,
        "paid_hours": paid_hours,
        "business_bp": business_bp,
    }
