"""Frozen test: bloom_accounting_tax.fixed_by_month (monthly depreciation and lease at business share). Fake numbers."""
import bloom_accounting_fixed as FX
import bloom_accounting_tax as T

SHARES = {"2026-10": {"bp": 5000}, "2026-11": {"bp": None}, "2026-12": {"bp": 10000}}
LEASED = {"id": "box2", "ownership": "leased", "lease_start": "2026-01-01", "lease_monthly_cents": 36500}
OWNED = {"id": "box1", "ownership": "owned", "in_service": "2026-03-01", "depreciation_method": "macrs5", "purchase_cents": 100000}
HW = {"id": 3, "kind": "cost", "category": "hardware", "amount_cents": 182600, "machine_id": None, "date": "2026-08-13"}


def test_machine_records_are_summed_at_each_months_share():
    s = {"machines": [LEASED, OWNED], "entry_machine_links": None}
    r = T.fixed_by_month(s, [], 2026, SHARES)
    assert list(r) == ["2026-10", "2026-11", "2026-12"]
    assert r["2026-10"]["lease_business_cents"] == 36500 * 12 * 31 // 365 // 2
    assert r["2026-11"]["lease_business_cents"] == 0 and r["2026-11"]["depreciation_business_cents"] == 0
    want = FX.machine_fixed_cents(OWNED, [], None, "2026-12-01", "2026-12-31", 10000)["depreciation_business_cents"]
    assert r["2026-12"]["depreciation_business_cents"] == want > 0


def test_machine_without_basis_makes_depreciation_none():
    s = {"machines": [{k: v for k, v in OWNED.items() if k != "purchase_cents"}], "entry_machine_links": None}
    r = T.fixed_by_month(s, [], 2026, SHARES)
    assert r["2026-10"]["depreciation_business_cents"] is None and r["2026-10"]["lease_business_cents"] == 0


def test_legacy_settings_used_when_no_machines():
    s = {"machines": None, "m4_in_service_date": "2026-10-01", "dep_method": "straight_line", "dep_life_months": 60,
         "m5_lease_monthly_cents": 10000, "m5_lease_months": 36, "m5_lease_start": "2026-10-01"}
    r = T.fixed_by_month(s, [HW], 2026, SHARES)
    assert r["2026-10"] == {"depreciation_business_cents": 182600 * 31 // 1826 // 2, "lease_business_cents": 10000 * 12 * 31 // 365 // 2}
    assert r["2026-11"] == {"depreciation_business_cents": 0, "lease_business_cents": 0}
    none = T.fixed_by_month({"machines": [], "m4_in_service_date": "2026-10-01"}, [], 2026, SHARES)
    assert none["2026-10"] == {"depreciation_business_cents": None, "lease_business_cents": None}
