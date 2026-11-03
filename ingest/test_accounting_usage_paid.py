"""Frozen test: bloom_accounting_usage.is_paid_minute / m4_business_bp (synthetic rows)."""
import bloom_accounting_usage as U


def r(ok=1, tok=10, other=0):
    return {"power_ok": ok, "tokens_delta": tok, "other_work": other}


def test_is_paid_minute_rules():
    assert U.is_paid_minute(r()) is True
    assert U.is_paid_minute(r(ok=0)) is False
    assert U.is_paid_minute(r(tok=0)) is False
    assert U.is_paid_minute(r(tok=None)) is False
    assert U.is_paid_minute(r(other=1)) is False
    assert U.is_paid_minute(r(other=None)) is True


def test_m4_business_bp_counts_only_measured_minutes():
    rows = [r()] * 3 + [r(tok=0)] * 1 + [r(ok=0)] * 6
    assert U.m4_business_bp(rows) == 7500


def test_m4_business_bp_edges():
    assert U.m4_business_bp([]) == 0
    assert U.m4_business_bp([r(ok=0)]) == 0
    assert U.m4_business_bp([r()] * 3) == 10000
    assert U.m4_business_bp([r()] + [r(tok=0)] * 2) == 3333


def test_sandbox_job_minute_is_paid_without_tokens():
    row = dict(r(tok=0), sandbox_jobs=1)
    assert U.is_paid_minute(row) is True
    assert U.is_paid_minute(dict(row, other_work=1)) is False
    assert U.is_paid_minute(dict(row, power_ok=0)) is False
    assert U.is_paid_minute(dict(r(tok=0), sandbox_jobs=0)) is False
