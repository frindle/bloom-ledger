"""Frozen test: each hardware entry is depreciated from the later of its own date and the Darkbloom start."""
import bloom_accounting_depr as DP
import bloom_accounting_fixed as F

S = {"m4_in_service_date": "2026-09-28", "dep_method": "macrs5", "dep_life_months": 60}
OLD = {"kind": "cost", "category": "hardware", "amount_cents": 322565, "machine_id": "m4", "date": "2026-08-13"}
NEW = {"kind": "cost", "category": "hardware", "amount_cents": 50000, "machine_id": "m4", "date": "2026-12-01"}


def test_later_purchase_starts_on_its_own_date():
    assert F.owned_depreciation_cents(S, [OLD, NEW], "2026-10-01", "2026-10-31") == DP.macrs5_cents(322565, "2026-09-28", "2026-10-01", "2026-10-31")
    dec = F.owned_depreciation_cents(S, [OLD, NEW], "2026-12-01", "2026-12-31")
    assert dec == DP.macrs5_cents(322565, "2026-09-28", "2026-12-01", "2026-12-31") + DP.macrs5_cents(50000, "2026-12-01", "2026-12-01", "2026-12-31")


def test_entry_without_date_uses_darkbloom_start_and_straight_line():
    sl = dict(S, dep_method="straight_line")
    nodate = {k: v for k, v in NEW.items() if k != "date"}
    got = F.owned_depreciation_cents(sl, [OLD, NEW, nodate], "2026-11-01", "2026-11-30")
    assert got == DP.straight_line_cents(322565, 60, "2026-09-28", "2026-11-01", "2026-11-30") + DP.straight_line_cents(50000, 60, "2026-09-28", "2026-11-01", "2026-11-30")


def test_machine_filter_and_unset_still_none():
    other = dict(NEW, machine_id="m5", date="2026-10-15")
    assert F.owned_depreciation_cents(S, [OLD, other], "2026-10-01", "2026-10-31", "m5") == DP.macrs5_cents(50000, "2026-10-15", "2026-10-01", "2026-10-31")
    assert F.owned_depreciation_cents(S, [OLD, other], "2026-10-01", "2026-10-31", "m9") is None
    assert F.owned_depreciation_cents(dict(S, m4_in_service_date=None), [OLD], "2026-10-01", "2026-10-31") is None
    assert "later of" in F.owned_depreciation_cents.__doc__
