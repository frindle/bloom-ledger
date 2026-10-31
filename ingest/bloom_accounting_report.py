"""Accounting report rows: per local day earnings and tokens from the indexed earnings table.

Days are local dates (settings local_timezone); money is integer micro-USD. Bookkeeping estimates, not tax advice."""
import datetime as dt
from zoneinfo import ZoneInfo


def ts_bounds(tz, start, end):
    """(first_ts, end_ts) UTC epoch seconds covering local dates start..end inclusive (end_ts is exclusive)."""
    zone = ZoneInfo(tz)
    s = dt.datetime.combine(dt.date.fromisoformat(start), dt.time(), zone)
    e = dt.datetime.combine(dt.date.fromisoformat(end) + dt.timedelta(days=1), dt.time(), zone)
    return int(s.timestamp()), int(e.timestamp())


def day_rows(db, tz, start, end, machine=None):
    """Per local day {"date", "earned_micro", "tokens", "wh", "minutes", "paid_minutes"} for days that have earnings, newest first.

    `machine` (optional) limits to earnings whose source_machine matches."""
    lo, hi = ts_bounds(tz, start, end)
    sql = "SELECT ts, micro_usd, completion_tokens FROM earnings WHERE ts >= ? AND ts < ?"
    args = [lo, hi]
    if machine:
        sql += " AND source_machine = ?"
        args.append(machine)
    days = {}
    zone = ZoneInfo(tz)

    def row_for(date):
        return days.setdefault(date, {"date": date, "earned_micro": 0, "tokens": 0, "wh": 0.0, "minutes": 0, "paid_minutes": 0})

    for ts, micro, tokens in db.execute(sql, args):
        d = dt.datetime.fromtimestamp(ts, zone).date().isoformat()
        row = row_for(d)
        row["earned_micro"] += micro
        row["tokens"] += tokens or 0

    psql = "SELECT ts, wh, power_ok, tokens_delta, other_work FROM power_minutes WHERE ts >= ? AND ts < ?"
    pargs = [lo, hi]
    if machine:
        psql += " AND machine_id = ?"
        pargs.append(machine)
    for ts, wh, power_ok, tokens_delta, other_work in db.execute(psql, pargs):
        d = dt.datetime.fromtimestamp(ts, zone).date().isoformat()
        row = row_for(d)
        if power_ok:
            row["wh"] += wh if wh is not None else 0.0
            row["minutes"] += 1
            td = tokens_delta if tokens_delta is not None else 0
            ow = other_work if other_work is not None else 0
            if td > 0 and not ow:
                row["paid_minutes"] += 1

    return [days[d] for d in sorted(days, reverse=True)]
