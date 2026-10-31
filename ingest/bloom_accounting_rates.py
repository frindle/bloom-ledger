"""Electricity rate lookup for the machine ledger: a user-entered schedule of seasons and time-of-day periods.

A schedule is a list of {"months": [..], "periods": [{"start": "HH:MM", "end": "HH:MM", "rate": "0.08415"}]}; rates are USD per kWh
decimal strings. Nothing is hardcoded here. Grid rates only; bookkeeping estimates, not tax advice."""
from decimal import Decimal


def _minutes(text):
    parts = text.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def rate_for(schedule, month, minute):
    if not schedule:
        return None
    for season in schedule:
        months = season.get("months", [])
        periods = season.get("periods", [])
        if month not in months:
            continue
        for period in periods:
            start_m = _minutes(period["start"])
            end_m = _minutes(period["end"])
            if start_m <= minute < end_m:
                return Decimal(str(period["rate"]))
    return None
