"""Electricity rate lookup for the machine ledger: a user-entered schedule of seasons and time-of-day periods.

A schedule is a list of {"months": [..], "periods": [{"start": "HH:MM", "end": "HH:MM", "rate": "0.08415"}]}; rates are USD per kWh
decimal strings. Nothing is hardcoded here. Grid rates only; bookkeeping estimates, not tax advice."""
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo


def _minutes(text):
    h, m = text.split(":")
    return int(h) * 60 + int(m)


def rate_for(schedule, month, minute):
    """USD per kWh (Decimal) for `month` (1-12) and `minute` of the local day (0-1439), or None when nothing matches.

    A period matches when start <= minute < end; the first matching season and period win."""
    for season in schedule or []:
        if month not in season.get("months", []):
            continue
        for p in season.get("periods", []):
            if _minutes(p["start"]) <= minute < _minutes(p["end"]):
                return Decimal(str(p["rate"]))
    return None


def _micro(x):
    """Round Decimal x (USD) to integer micro-USD with ROUND_HALF_UP."""
    return int((x * 1000000).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def interval_cost(settings, ts, wh):
    """Turn a metered interval into a cost from the entered rate schedule."""
    schedule = settings.get("rate_schedule")
    adder = settings.get("rate_adder_usd_per_kwh")
    universal = settings.get("universal_charge_usd_per_kwh")
    county = settings.get("county_fee_pct")
    if any(v is None for v in [schedule, adder, universal, county]):
        return None
    tz = ZoneInfo(settings.get("local_timezone") or "UTC")
    local = dt.datetime.fromtimestamp(ts, tz)
    rate = rate_for(schedule, local.month, local.hour * 60 + local.minute)
    if rate is None:
        return None
    kwh = Decimal(str(wh)) / 1000
    base = kwh * (rate + Decimal(str(adder)))
    energy_micro = _micro(base)
    fee_micro = _micro(base * Decimal(str(county)) / 100)
    uec_micro = _micro(kwh * Decimal(str(universal)))
    total_micro = energy_micro + fee_micro + uec_micro
    return {
        "energy_micro": energy_micro,
        "fee_micro": fee_micro,
        "uec_micro": uec_micro,
        "total_micro": total_micro,
    }
