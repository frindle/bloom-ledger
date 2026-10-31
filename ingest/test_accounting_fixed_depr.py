"""Frozen test: owned hardware depreciation from entries and settings."""
import bloom_accounting_fixed as F

E = [{"kind": "cost", "category": "hardware", "amount_cents": 300000, "machine_id": "m4"},
     {"kind": "cost", "category": "software", "amount_cents": 999, "machine_id": "m4"},
     {"kind": "receipt", "category": "hardware", "amount_cents": 5, "machine_id": "m4"},
     {"kind": "cost", "category": "hardware", "amount_cents": 20000, "machine_id": "other"}]
S = {"m4_in_service_date": "2026-10-01", "dep_method": "straight_line", "dep_life_months": 60}


def test_basis_sums_hardware_costs_only():
    assert F.depreciation_basis_cents(E) == 320000
    assert F.depreciation_basis_cents(E, "m4") == 300000
    assert F.depreciation_basis_cents([E[1], E[2]]) is None


def test_depreciation_methods_and_unset():
    assert F.owned_depreciation_cents(S, E, "2026-10-01", "2026-10-01", "m4") == 300000 * 1 // 1826
    assert F.owned_depreciation_cents(dict(S, dep_method="section179"), E, "2026-10-01", "2026-10-31", "m4") == 300000
    assert F.owned_depreciation_cents(S, [E[1]], "2026-10-01", "2026-10-31") is None
    assert F.owned_depreciation_cents(dict(S, m4_in_service_date=None), E, "2026-10-01", "2026-10-31") is None
