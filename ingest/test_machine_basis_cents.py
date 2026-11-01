"""Frozen test: bloom_accounting_fixed.machine_basis_cents (hardware cost entries attached to a machine). Fake numbers."""
import bloom_accounting_fixed as F

M1 = {"id": "box1", "ownership": "owned", "purchase_cents": 70000}
ENTRIES = [
    {"id": 1, "kind": "cost", "category": "hardware", "amount_cents": 40000, "machine_id": "box1", "date": "2026-01-05"},
    {"id": 2, "kind": "cost", "category": "hardware", "amount_cents": 25000, "machine_id": None, "date": "2026-01-06"},
    {"id": 3, "kind": "cost", "category": "software", "amount_cents": 9000, "machine_id": "box1", "date": "2026-01-07"},
    {"id": 4, "kind": "receipt", "category": "hardware", "amount_cents": 8000, "machine_id": "box1", "date": "2026-01-08"},
    {"id": 5, "kind": "cost", "category": "hardware", "amount_cents": 3000, "machine_id": "box2", "date": "2026-01-09"},
]


def test_entries_tagged_with_the_machine_are_summed():
    assert F.machine_basis_cents(M1, ENTRIES) == 40000
    assert F.machine_basis_cents({"id": "box2"}, ENTRIES) == 3000


def test_a_link_attaches_an_untagged_entry_and_overrides_a_tag():
    assert F.machine_basis_cents(M1, ENTRIES, {"2": "box1"}) == 65000
    assert F.machine_basis_cents(M1, ENTRIES, {"1": "box2"}) == 70000
    assert F.machine_basis_cents({"id": "box2"}, ENTRIES, {"1": "box2"}) == 43000


def test_falls_back_to_purchase_cents_then_none():
    assert F.machine_basis_cents(M1, []) == 70000
    assert F.machine_basis_cents({"id": "box9"}, ENTRIES) is None
    assert F.machine_basis_cents({"id": "box9", "purchase_cents": 12345}, ENTRIES, {}) == 12345
