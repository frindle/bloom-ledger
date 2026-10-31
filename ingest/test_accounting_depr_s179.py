"""Frozen test: bloom_accounting_depr.section179_cents / macrs5_year_amounts."""
import bloom_accounting_depr as D


def test_section179_only_in_the_in_service_range():
    assert D.section179_cents(100000, "2026-10-01", "2026-10-01", "2026-10-31") == 100000
    assert D.section179_cents(100000, "2026-10-01", "2026-10-02", "2026-12-31") == 0
    assert D.section179_cents(100000, "2026-10-01", "2026-01-01", "2026-09-30") == 0
    assert D.section179_cents(100000, "2026-10-31", "2026-10-01", "2026-10-31") == 100000


def test_macrs5_amounts_round_numbers():
    assert D.macrs5_year_amounts(100000) == [20000, 32000, 19200, 11520, 11520, 5760]


def test_macrs5_amounts_sum_to_basis_with_odd_basis():
    for basis in (1, 99, 322565, 1000003):
        a = D.macrs5_year_amounts(basis)
        assert len(a) == 6 and sum(a) == basis and min(a) >= 0
