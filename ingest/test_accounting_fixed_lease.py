"""Frozen test: bloom_accounting_fixed.lease_cents."""
import bloom_accounting_fixed as F

S = {"m5_lease_monthly_cents": 10000, "m5_lease_months": 36, "m5_lease_start": "2026-11-01"}


def test_unset_inputs_give_none():
    assert F.lease_cents({}, "2026-11-01", "2026-11-30") is None
    assert F.lease_cents(dict(S, m5_lease_start=None), "2026-11-01", "2026-11-30") is None
    assert F.lease_cents(dict(S, m5_lease_monthly_cents=None), "2026-11-01", "2026-11-30") is None


def test_before_start_is_zero_and_periods_add_up():
    assert F.lease_cents(S, "2026-10-01", "2026-10-31") == 0
    a = F.lease_cents(S, "2026-11-01", "2026-11-15")
    b = F.lease_cents(S, "2026-11-16", "2026-12-31")
    assert a + b == F.lease_cents(S, "2026-11-01", "2026-12-31") == 10000 * 12 * 61 // 365


def test_capped_at_the_term_total():
    assert F.lease_cents(S, "2026-11-01", "2040-01-01") == 360000
