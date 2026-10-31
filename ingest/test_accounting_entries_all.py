"""Frozen test: all_entries includes voided entries with a flag."""
import sqlite3

import bloom_accounting_entries as E


def test_voided_entries_are_listed_and_flagged():
    db = sqlite3.connect(":memory:")
    a = E.add_entry(db, {"kind": "cost", "date": "2026-10-20", "amount_cents": 5, "category": "other"}, 1)
    b = E.add_entry(db, {"kind": "receipt", "date": "2026-10-21", "amount_cents": 7, "category": "other", "machine_id": "m4"}, 2)
    assert E.void_entry(db, a, 3)
    rows = E.all_entries(db)
    assert [(r["id"], r["voided"]) for r in rows] == [(a, True), (b, False)]
    assert rows[1]["machine_id"] == "m4" and rows[1]["amount_cents"] == 7


def test_current_entries_unchanged_and_date_filter():
    db = sqlite3.connect(":memory:")
    a = E.add_entry(db, {"kind": "cost", "date": "2026-10-20", "amount_cents": 5, "category": "other"}, 1)
    b = E.add_entry(db, {"kind": "cost", "date": "2026-10-21", "amount_cents": 7, "category": "other"}, 2)
    E.void_entry(db, a, 3)
    assert [r["id"] for r in E.current_entries(db)] == [b]
    assert [r["id"] for r in E.all_entries(db, "2026-10-21", "2026-10-21")] == [b]
    assert [r["id"] for r in E.all_entries(db, "2026-10-22")] == []
