"""Frozen test: bloom_accounting_summary.machine_breakdown (per-machine depreciation and lease rows). Fake numbers."""
import bloom_accounting_summary as SM

OWNED = {"id": "box1", "display_name": "Box One", "ownership": "owned", "in_service": "2026-03-01",
         "depreciation_method": "macrs5", "purchase_cents": 100000}
LEASED = {"id": "box2", "display_name": "Box Two", "ownership": "leased", "lease_start": "2026-01-01", "lease_monthly_cents": 36500}
HW = {"id": 7, "kind": "cost", "category": "hardware", "amount_cents": 50000, "machine_id": None, "date": "2026-01-02"}


def test_no_machines_means_no_rows():
    assert SM.machine_breakdown({}, [], "2026-01-01", "2026-12-31") == []
    assert SM.machine_breakdown({"machines": None, "entry_machine_links": None}, [HW], "2026-01-01", "2026-12-31") == []
    assert SM.machine_breakdown({"machines": []}, [], "2026-01-01", "2026-12-31") == []


def test_one_row_per_machine_with_gross_cents():
    rows = SM.machine_breakdown({"machines": [OWNED, LEASED]}, [], "2026-01-01", "2026-12-31")
    assert rows == [
        {"id": "box1", "display_name": "Box One", "ownership": "owned", "depreciation_cents": 20000, "lease_cents": 0},
        {"id": "box2", "display_name": "Box Two", "ownership": "leased", "depreciation_cents": 0, "lease_cents": 36500 * 12},
    ]


def test_linked_hardware_entry_sets_the_basis_and_no_basis_is_none():
    s = {"machines": [OWNED], "entry_machine_links": {"7": "box1"}}
    assert SM.machine_breakdown(s, [HW], "2026-01-01", "2026-12-31")[0]["depreciation_cents"] == 10000
    bare = {k: v for k, v in OWNED.items() if k != "purchase_cents"}
    assert SM.machine_breakdown({"machines": [bare]}, [], "2026-01-01", "2026-12-31")[0]["depreciation_cents"] is None
