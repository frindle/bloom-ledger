"""Frozen test: bloom_accounting_entries.create_entries_table / add_entry."""
import pytest

import bloom_accounting_entries as E
import bloom_ingest as I


def mk(tmp_path):
    return I.open_db(tmp_path / "i.sqlite")


def good(**kw):
    e = {"kind": "cost", "date": "2026-10-20", "amount_cents": 1234, "category": "software"}
    e.update(kw)
    return e


def test_add_returns_incrementing_ids_and_stores_row(tmp_path):
    db = mk(tmp_path)
    a = E.add_entry(db, good(machine_id="m1", note="n"), 100)
    b = E.add_entry(db, good(amount_cents=5), 101)
    assert b == a + 1
    row = db.execute("SELECT kind, date, amount_cents, category, machine_id, note, created_at, voided_at"
                     " FROM acct_entries WHERE id = ?", (a,)).fetchone()
    assert tuple(row) == ("cost", "2026-10-20", 1234, "software", "m1", "n", 100, None)


def test_invalid_entry_raises_and_stores_nothing(tmp_path):
    db = mk(tmp_path)
    E.create_entries_table(db)
    with pytest.raises(ValueError, match="bad amount"):
        E.add_entry(db, good(amount_cents=-1), 100)
    assert db.execute("SELECT COUNT(*) FROM acct_entries").fetchone()[0] == 0


def test_create_table_is_idempotent(tmp_path):
    db = mk(tmp_path)
    E.create_entries_table(db)
    E.create_entries_table(db)
    cols = [r[1] for r in db.execute("PRAGMA table_info(acct_entries)")]
    assert cols == ["id", "kind", "date", "amount_cents", "category", "machine_id", "note", "created_at", "voided_at", "vendor", "purpose", "business_pct", "receipt"]
