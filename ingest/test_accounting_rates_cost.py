"""Frozen test: bloom_accounting_rates.interval_cost (winter, summer off-peak, summer on-peak; unset inputs)."""
import datetime as dt

import bloom_accounting_rates as R

SCHED = [
    {"months": [10, 11, 12, 1, 2, 3, 4, 5], "periods": [{"start": "00:00", "end": "24:00", "rate": "0.08415"}]},
    {"months": [6, 7, 8, 9], "periods": [
        {"start": "00:00", "end": "18:01", "rate": "0.07062"},
        {"start": "18:01", "end": "21:00", "rate": "0.46912"},
        {"start": "21:00", "end": "24:00", "rate": "0.07062"}]},
]

S = {"rate_schedule": SCHED, "rate_adder_usd_per_kwh": "0.00096", "universal_charge_usd_per_kwh": "0.00039",
     "county_fee_pct": "5", "local_timezone": "America/Los_Angeles"}


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def test_winter_noon_local():
    assert R.interval_cost(S, utc(2026, 1, 15, 20, 0), 1000) == {
        "energy_micro": 85110, "fee_micro": 4256, "uec_micro": 390, "total_micro": 89756}


def test_summer_off_peak_and_on_peak_use_local_time():
    off = R.interval_cost(S, utc(2026, 7, 15, 19, 0), 1000)
    assert off["energy_micro"] == 71580 and off["fee_micro"] == 3579 and off["total_micro"] == 75549
    on = R.interval_cost(S, utc(2026, 7, 16, 2, 0), 1000)
    assert on["energy_micro"] == 470080 and on["fee_micro"] == 23504 and on["total_micro"] == 493974
    assert R.interval_cost(S, utc(2026, 7, 16, 2, 0), 500)["total_micro"] == 246987


def test_unset_input_gives_none():
    assert R.interval_cost(dict(S, county_fee_pct=None), utc(2026, 1, 15, 20, 0), 1000) is None
    assert R.interval_cost(dict(S, rate_schedule=None), utc(2026, 1, 15, 20, 0), 1000) is None
    assert R.interval_cost({}, utc(2026, 1, 15, 20, 0), 1000) is None
