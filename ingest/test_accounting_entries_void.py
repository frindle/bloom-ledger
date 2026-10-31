"""Frozen test: bloom_accounting_entries.void_entry / current_entries."""
import bloom_accounting_entries as E
import bloom_ingest as I


def mk(tmp_path):
    return I.open_db(tmp_path / "i.sqlite")


def add(db, date, cents, **kw):
    e = {"kind": "cost", "date": date, "amount_cents": cents, "category": "other"}
    e.update(kw)
    return E.add_entry(db, e, 1)


def test_void_hides_entry_keeps_row_and_is_not_repeatable(tmp_path):
    db = mk(tmp_path)
    a = add(db, "2026-10-20", 100)
    assert E.void_entry(db, a, 50) is True
    assert E.void_entry(db, a, 60) is False
    assert E.void_entry(db, 999, 60) is False
    assert E.current_entries(db) == []
    assert db.execute("SELECT voided_at FROM acct_entries WHERE id = ?", (a,)).fetchone()[0] == 50


def test_current_entries_ordering_and_fields(tmp_path):
    db = mk(tmp_path)
    b = add(db, "2026-11-02", 7)
    a = add(db, "2026-10-20", 5, machine_id="m1", note="x")
    c = add(db, "2026-10-20", 6)
    rows = E.current_entries(db)
    assert [r["id"] for r in rows] == [a, c, b]
    assert rows[0] == {"id": a, "kind": "cost", "date": "2026-10-20", "amount_cents": 5, "category": "other",
                       "machine_id": "m1", "note": "x"}


def test_inclusive_date_bounds(tmp_path):
    db = mk(tmp_path)
    for d in ("2026-10-01", "2026-10-15", "2026-10-31", "2026-11-01"):
        add(db, d, 1)
    got = [r["date"] for r in E.current_entries(db, "2026-10-15", "2026-10-31")]
    assert got == ["2026-10-15", "2026-10-31"]
    assert [r["date"] for r in E.current_entries(db, start="2026-10-31")] == ["2026-10-31", "2026-11-01"]
    assert [r["date"] for r in E.current_entries(db, end="2026-10-01")] == ["2026-10-01"]
