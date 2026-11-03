"""Frozen test: entries store vendor, purpose, business_pct and a receipt file name; older tables are migrated."""
import sqlite3

import pytest

import bloom_accounting_entries as E

BASE = {"kind": "cost", "date": "2026-10-20", "amount_cents": 4999, "category": "hardware"}
OLD = ("CREATE TABLE acct_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, date TEXT NOT NULL,"
       " amount_cents INTEGER NOT NULL, category TEXT NOT NULL, machine_id TEXT, note TEXT,"
       " created_at INTEGER NOT NULL, voided_at INTEGER)")
COLS = ["id", "kind", "date", "amount_cents", "category", "machine_id", "note", "created_at", "voided_at",
        "vendor", "purpose", "business_pct", "receipt"]


def cols(db):
    return [r[1] for r in db.execute("PRAGMA table_info(acct_entries)")]


def test_old_table_is_migrated_and_old_rows_default_to_full_business_use():
    db = sqlite3.connect(":memory:")
    db.execute(OLD)
    db.execute("INSERT INTO acct_entries (kind, date, amount_cents, category, created_at) VALUES"
               " ('cost', '2026-10-01', 500, 'other', 1)")
    db.commit()
    E.create_entries_table(db)
    E.create_entries_table(db)
    assert [r["business_pct"] for r in E.all_entries(db)] == [100]
    assert cols(db) == COLS
    row = E.current_entries(db)[0]
    assert (row["vendor"], row["purpose"], row["business_pct"], row["receipt"]) == (None, None, 100, None)


def test_new_table_has_record_columns():
    db = sqlite3.connect(":memory:")
    E.create_entries_table(db)
    assert cols(db) == COLS


def test_add_stores_record_fields_and_defaults_pct():
    db = sqlite3.connect(":memory:")
    a = E.add_entry(db, dict(BASE, vendor="B&H", purpose="Fan for M4", business_pct=60, note="n"), 7)
    b = E.add_entry(db, dict(BASE, amount_cents=10), 8)
    rows = {r["id"]: r for r in E.current_entries(db)}
    assert rows[a] == {"id": a, "kind": "cost", "date": "2026-10-20", "amount_cents": 4999, "category": "hardware",
                       "machine_id": None, "note": "n", "vendor": "B&H", "purpose": "Fan for M4",
                       "business_pct": 60, "receipt": None}
    assert rows[b]["business_pct"] == 100 and rows[b]["vendor"] is None
    assert E.all_entries(db)[0] == rows[a] | {"voided": False}
    with pytest.raises(ValueError, match="bad business_pct"):
        E.add_entry(db, dict(BASE, business_pct=0), 9)


def test_docstrings_describe_records():
    assert "business_pct" in (E.create_entries_table.__doc__ or "")
    assert "receipt" in (E.current_entries.__doc__ or "") and "vendor" in (E.all_entries.__doc__ or "")
