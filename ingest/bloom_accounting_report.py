"""Accounting report rows: per local day earnings and tokens from the indexed earnings table.

Days are local dates (settings local_timezone); money is integer micro-USD. Bookkeeping estimates, not tax advice."""
import datetime as dt
from zoneinfo import ZoneInfo


def ts_bounds(tz, start, end):
    sd = dt.datetime.strptime(start, "%Y-%m-%d").date()
    ed = dt.datetime.strptime(end, "%Y-%m-%d").date() + dt.timedelta(days=1)
    first = int(dt.datetime.combine(sd, dt.time(), ZoneInfo(tz)).timestamp())
    last = int(dt.datetime.combine(ed, dt.time(), ZoneInfo(tz)).timestamp())
    return (first, last)


def day_rows(db, tz, start, end, machine=None):
    first_ts, end_ts = ts_bounds(tz, start, end)
    params = [first_ts, end_ts]
    where = "ts >= ? AND ts < ?"
    if machine:
        where += " AND source_machine = ?"
        params.append(machine)
    rows = db.execute(
        f"SELECT ts, micro_usd, completion_tokens FROM earnings WHERE {where}", params
    ).fetchall()
    groups = {}
    for ts, micro, tokens in rows:
        local_date = dt.datetime.fromtimestamp(ts, ZoneInfo(tz)).date().isoformat()
        if local_date not in groups:
            groups[local_date] = {"date": local_date, "earned_micro": 0, "tokens": 0}
        groups[local_date]["earned_micro"] += micro
        groups[local_date]["tokens"] += tokens if tokens is not None else 0
    return sorted(groups.values(), key=lambda g: g["date"], reverse=True)
