"""Frozen test: attach_receipt records a receipt file name on a live entry."""
import sqlite3

import pytest

import bloom_accounting_entries as E

BASE = {"kind": "cost", "date": "2026-10-20", "amount_cents": 4999, "category": "hardware"}


def test_attach_receipt_on_live_entries_only():
    db = sqlite3.connect(":memory:")
    a = E.add_entry(db, BASE, 1)
    b = E.add_entry(db, BASE, 2)
    E.void_entry(db, b, 3)
    attach = getattr(E, "attach_receipt", None)
    assert attach is not None, "attach_receipt missing"
    assert attach(db, a, "12-fan-invoice.pdf") is True
    assert attach(db, b, "x.pdf") is False and attach(db, 999, "x.pdf") is False
    assert E.current_entries(db)[0]["receipt"] == "12-fan-invoice.pdf"
    every = {r["id"]: r for r in E.all_entries(db)}
    assert every[a]["receipt"] == "12-fan-invoice.pdf" and every[b]["receipt"] is None and every[b]["voided"] is True
    assert every[a]["business_pct"] == 100 and "vendor" in every[a] and "purpose" in every[a]
    for bad in ("", "../x.pdf", "a/b.pdf", "a\\b.pdf", ".hidden", "x" * 201, None, 5):
        with pytest.raises(ValueError, match="bad receipt"):
            attach(db, a, bad)
    assert E.current_entries(db)[0]["receipt"] == "12-fan-invoice.pdf"


def test_attach_receipt_docstring():
    E.create_entries_table(sqlite3.connect(":memory:"))
    attach = getattr(E, "attach_receipt", None)
    assert attach is not None and "separator" in (attach.__doc__ or "")
