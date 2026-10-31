"""Frozen test: bloom_accounting_usage.personal_minutes."""
import bloom_accounting_usage as U


def test_half_open_windows():
    ts = [100, 160, 220, 280]
    assert U.personal_minutes([(160, 280)], ts) == 2
    assert U.personal_minutes([(100, 101)], ts) == 1
    assert U.personal_minutes([(281, 400)], ts) == 0


def test_overlapping_windows_count_once_and_empty():
    ts = [100, 160, 220]
    assert U.personal_minutes([(100, 200), (150, 300)], ts) == 3
    assert U.personal_minutes([], ts) == 0
    assert U.personal_minutes([(0, 1000)], []) == 0
