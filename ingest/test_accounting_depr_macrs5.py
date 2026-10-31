"""Frozen test: bloom_accounting_depr.macrs5_cents."""
import bloom_accounting_depr as D

INS = "2026-03-01"


def test_each_calendar_year_gets_its_table_amount():
    assert D.macrs5_cents(100000, INS, "2026-01-01", "2026-12-31") == 20000
    assert D.macrs5_cents(100000, INS, "2027-01-01", "2027-12-31") == 32000
    assert D.macrs5_cents(100000, INS, "2028-01-01", "2028-12-31") == 19200
    assert D.macrs5_cents(100000, INS, "2031-01-01", "2031-12-31") == 5760


def test_total_before_start_and_after_end():
    assert D.macrs5_cents(100000, INS, "2026-01-01", "2040-12-31") == 100000
    assert D.macrs5_cents(100000, INS, "2026-01-01", "2026-02-28") == 0
    assert D.macrs5_cents(100000, INS, "2032-01-01", "2040-12-31") == 0


def test_split_ranges_add_up_exactly():
    basis = 322565
    whole = D.macrs5_cents(basis, INS, "2026-03-01", "2027-12-31")
    parts = sum(D.macrs5_cents(basis, INS, a, b) for a, b in
                (("2026-03-01", "2026-06-30"), ("2026-07-01", "2026-12-31"), ("2027-01-01", "2027-08-15"),
                 ("2027-08-16", "2027-12-31")))
    assert whole == parts
