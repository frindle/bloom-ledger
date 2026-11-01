"""Frozen test: bloom_accounting_fixed.machine_fixed_cents (per-machine depreciation and lease). Fake numbers."""
import bloom_accounting_fixed as F

OWNED = {"id": "box1", "ownership": "owned", "in_service": "2026-03-01", "depreciation_method": "macrs5", "purchase_cents": 100000}
LEASED = {"id": "box2", "ownership": "leased", "lease_start": "2026-01-01", "lease_monthly_cents": 36500}
ENTRY = {"id": 7, "kind": "cost", "category": "hardware", "amount_cents": 50000, "machine_id": None, "date": "2026-01-02"}


def test_owned_machine_uses_macrs_on_its_basis():
    r = F.machine_fixed_cents(OWNED, [], None, "2026-01-01", "2026-12-31")
    assert r == {"depreciation_cents": 20000, "depreciation_business_cents": 20000, "lease_cents": 0, "lease_business_cents": 0}
    r = F.machine_fixed_cents(OWNED, [ENTRY], {"7": "box1"}, "2027-01-01", "2027-12-31", 5000)
    assert r["depreciation_cents"] == 16000 and r["depreciation_business_cents"] == 8000
    assert F.machine_fixed_cents(dict(OWNED, depreciation_method="straight_line"), [], None, "2026-01-01", "2040-12-31")["depreciation_cents"] == 100000


def test_machine_record_elections_and_yearly_business_use_apply():
    m = dict(OWNED, section179_cents=40000, business_use_bp={"2026": 2500})
    r = F.machine_fixed_cents(m, [], None, "2026-03-01", "2026-03-01", 9000)
    assert r["depreciation_cents"] >= 40000 and r["depreciation_business_cents"] == r["depreciation_cents"] // 4
    r2 = F.machine_fixed_cents(m, [], None, "2027-01-01", "2027-12-31", 9000)
    assert r2["depreciation_cents"] == 19200 and r2["depreciation_business_cents"] == 19200 * 9000 // 10000


def test_leased_machine_accrues_daily_at_business_share():
    r = F.machine_fixed_cents(LEASED, [], None, "2026-01-01", "2026-01-31", 5000)
    assert r["lease_cents"] == 36500 * 12 * 31 // 365 and r["lease_business_cents"] == r["lease_cents"] // 2
    assert r["depreciation_cents"] == 0 and r["depreciation_business_cents"] == 0
    assert F.machine_fixed_cents(dict(LEASED, lease_months=1), [], None, "2026-01-01", "2026-12-31")["lease_cents"] == 36500
    assert F.machine_fixed_cents(LEASED, [], None, "2025-01-01", "2025-12-31")["lease_cents"] == 0


def test_owned_machine_without_basis_gives_none():
    m = {k: v for k, v in OWNED.items() if k != "purchase_cents"}
    r = F.machine_fixed_cents(m, [], None, "2026-01-01", "2026-12-31")
    assert r["depreciation_cents"] is None and r["depreciation_business_cents"] is None and r["lease_cents"] == 0
