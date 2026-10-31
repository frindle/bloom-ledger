"""Frozen test: bloom_accounting_rates.rate_for (schedule is user-entered data)."""
from decimal import Decimal

import bloom_accounting_rates as R

SCHED = [
    {"months": [10, 11, 12, 1, 2, 3, 4, 5], "periods": [{"start": "00:00", "end": "24:00", "rate": "0.08415"}]},
    {"months": [6, 7, 8, 9], "periods": [
        {"start": "00:00", "end": "18:01", "rate": "0.07062"},
        {"start": "18:01", "end": "21:00", "rate": "0.46912"},
        {"start": "21:00", "end": "24:00", "rate": "0.07062"}]},
]


def test_winter_is_flat():
    assert R.rate_for(SCHED, 1, 0) == Decimal("0.08415")
    assert R.rate_for(SCHED, 12, 1439) == Decimal("0.08415")


def test_summer_on_and_off_peak_edges():
    assert R.rate_for(SCHED, 7, 18 * 60) == Decimal("0.07062")
    assert R.rate_for(SCHED, 7, 18 * 60 + 1) == Decimal("0.46912")
    assert R.rate_for(SCHED, 7, 20 * 60 + 59) == Decimal("0.46912")
    assert R.rate_for(SCHED, 7, 21 * 60) == Decimal("0.07062")
    assert R.rate_for(SCHED, 6, 12 * 60) == Decimal("0.07062") and R.rate_for(SCHED, 9, 19 * 60) == Decimal("0.46912")


def test_unset_or_unmatched_is_none():
    assert R.rate_for(None, 7, 0) is None and R.rate_for([], 7, 0) is None
    assert R.rate_for([{"months": [1]}, {"months": [7], "periods": [{"start": "01:00", "end": "02:00", "rate": "1"}]}], 7, 0) is None
