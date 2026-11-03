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


def minute_stream(ok, tok, other, sbx):
    """Which stream a power minute belongs to: "sandbox", "gpu", "other" (Penn's own work), "idle", or "gap" (no reading)."""
    if not ok:
        return "gap"
    if other:
        return "other"
    if (sbx or 0) > 0:
        return "sandbox"
    if (tok or 0) > 0:
        return "gpu"
    return "idle"


def stream_of_kind(kind):
    """Earnings kind -> stream. Base rewards come from serving Darkbloom GPU inference, so they count as GPU."""
    return "sandbox" if kind == "sandbox" else "gpu"


def _blank_row(d, settings):
    return {"date": d, "earned_micro": 0, "gpu_micro": 0, "sandbox_micro": 0,
            "gpu_cost_micro": 0, "sandbox_cost_micro": 0, "gpu_minutes": 0, "sandbox_minutes": 0, "other_minutes": 0,
            "tokens": 0, "wh": 0.0, "minutes": 0, "paid_minutes": 0, "cost_micro": 0 if settings else None}


def day_rows(db, tz, start, end, machine=None, settings=None):
    """Per local day totals, split into the Darkbloom GPU and Sandbox streams, newest first.

    `machine` (optional) limits to earnings whose source_machine matches. A stream's power cost is the cost of the
    minutes that stream was working; idle and other-work minutes stay in the day's total cost only."""
    lo, hi = ts_bounds(tz, start, end)
    sql = "SELECT ts, micro_usd, completion_tokens, kind FROM earnings WHERE ts >= ? AND ts < ?"
    args = [lo, hi]
    if machine:
        sql += " AND source_machine = ?"
        args.append(machine)
    days = {}
    zone = ZoneInfo(tz)

    def row_for(d):
        return days.setdefault(d, _blank_row(d, settings))
    for ts, micro, tokens, kind in db.execute(sql, args):
        row = row_for(dt.datetime.fromtimestamp(ts, zone).date().isoformat())
        row["earned_micro"] += micro
        row[stream_of_kind(kind) + "_micro"] += micro
        row["tokens"] += tokens or 0
    psql = "SELECT ts, wh, power_ok, tokens_delta, other_work, sandbox_jobs FROM power_minutes WHERE ts >= ? AND ts < ?"
    pargs = [lo, hi]
    if machine:
        psql += " AND machine_id = ?"
        pargs.append(machine)
    for ts, wh, ok, tok, other, sbx in db.execute(psql, pargs):
        row = row_for(dt.datetime.fromtimestamp(ts, zone).date().isoformat())
        if not ok:
            continue
        row["wh"] += wh or 0.0
        row["minutes"] += 1
        c = None
        if settings and row["cost_micro"] is not None:
            c = RT.interval_cost(settings, ts, wh or 0.0)
            row["cost_micro"] = None if c is None else row["cost_micro"] + c["total_micro"]
        st = minute_stream(ok, tok, other, sbx)
        if st == "other":
            row["other_minutes"] += 1
        elif st in ("gpu", "sandbox"):
            row["paid_minutes"] += 1
            row[st + "_minutes"] += 1
            if c is not None:
                row[st + "_cost_micro"] += c["total_micro"]
    return [days[d] for d in sorted(days, reverse=True)]


def day_detail(db, tz, date, machine=None, settings=None):
    """One local day's individual logs: every earnings entry, every power minute, and hourly roll-ups.

    Times are given as local "HH:MM" strings so the page needs no time-zone code."""
    lo, hi = ts_bounds(tz, date, date)
    zone = ZoneInfo(tz)
    sql = "SELECT ts, micro_usd, completion_tokens, kind, model, job_id FROM earnings WHERE ts >= ? AND ts < ?"
    args = [lo, hi]
    if machine:
        sql += " AND source_machine = ?"
        args.append(machine)
    hours = [{"hour": h, "wh": 0.0, "cost_micro": 0 if settings else None, "earned_micro": 0, "gpu_micro": 0,
              "sandbox_micro": 0, "gpu": 0, "sandbox": 0, "other": 0, "idle": 0, "gap": 0} for h in range(24)]
    earnings = []
    for ts, micro, tokens, kind, model, job_id in db.execute(sql + " ORDER BY ts", args):
        local = dt.datetime.fromtimestamp(ts, zone)
        st = stream_of_kind(kind)
        earnings.append({"ts": ts, "time": local.strftime("%H:%M:%S"), "stream": st, "kind": kind or "job",
                         "model": model or "", "job_id": job_id or "", "micro_usd": micro, "tokens": tokens or 0})
        h = hours[local.hour]
        h["earned_micro"] += micro
        h[st + "_micro"] += micro
    psql = ("SELECT ts, wh, power_ok, tokens_delta, other_work, sandbox_jobs, dbk_state FROM power_minutes"
            " WHERE ts >= ? AND ts < ?")
    pargs = [lo, hi]
    if machine:
        psql += " AND machine_id = ?"
        pargs.append(machine)
    minutes = []
    for ts, wh, ok, tok, other, sbx, state in db.execute(psql + " ORDER BY ts", pargs):
        local = dt.datetime.fromtimestamp(ts, zone)
        st = minute_stream(ok, tok, other, sbx)
        c = RT.interval_cost(settings, ts, wh or 0.0) if settings and ok else None
        cost = None if c is None else c["total_micro"]
        minutes.append({"ts": ts, "time": local.strftime("%H:%M"), "slot": local.hour * 60 + local.minute,
                        "stream": st, "wh": round(wh or 0.0, 3) if ok else 0.0, "cost_micro": cost,
                        "tokens": tok or 0, "sandbox_jobs": sbx or 0, "state": state or ""})
        h = hours[local.hour]
        h[st] += 1
        if ok:
            h["wh"] += wh or 0.0
            if h["cost_micro"] is not None:
                h["cost_micro"] = None if cost is None else h["cost_micro"] + cost
    for h in hours:
        h["wh"] = round(h["wh"], 3)
    return {"date": date, "tz": tz, "earnings": earnings, "minutes": minutes,
            "hours": [h for h in hours if h["earned_micro"] or any(h[k] for k in ("gpu", "sandbox", "other", "idle", "gap"))]}


def totals(rows):
    """Aggregate day_rows into period figures."""
    earned_micro = 0
    split = {k: 0 for k in ("gpu_micro", "sandbox_micro", "gpu_cost_micro", "sandbox_cost_micro", "gpu_minutes",
                            "sandbox_minutes", "other_minutes")}
    tokens = 0
    wh = 0.0
    minutes = 0
    paid_minutes = 0
    cost_micro = 0
    cost_none = False
    for r in rows:
        earned_micro += r["earned_micro"]
        for k in split:
            split[k] += r.get(k, 0)
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
        **split,
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
