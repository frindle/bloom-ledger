"""Frozen test: receipt download. Fake data."""
import hashlib
import sqlite3

import bloom_accounting_entries as AE
import bloom_accounting_receipts as R

PDF = b"%PDF-1.4 fake receipt\n"


def make():
    db = sqlite3.connect(":memory:")
    a = AE.add_entry(db, {"kind": "cost", "date": "2026-10-05", "amount_cents": 1200, "category": "software"}, 1)
    b = AE.add_entry(db, {"kind": "cost", "date": "2026-10-06", "amount_cents": 300, "category": "supplies"}, 1)
    AE.void_entry(db, b, 2)
    return db, a, b


def test_get_served(tmp_path):
    db, a, b = make()
    assert R.receipt_post(db, tmp_path, a, "application/pdf", PDF)[0] == 201
    assert R.receipt_get(db, tmp_path, a) == (200, "application/pdf", PDF)
    R.receipt_post(db, tmp_path, a, "image/webp", b"webp")
    assert R.receipt_get(db, tmp_path, a) == (200, "image/webp", b"webp")
    AE.void_entry(db, a, 3)
    assert R.receipt_get(db, tmp_path, a) == (200, "image/webp", b"webp")


def test_get_missing(tmp_path):
    db, a, b = make()
    nf = (404, "application/json", b'{"error": "not found"}')
    assert R.receipt_get(db, tmp_path, a) == nf and R.receipt_get(db, tmp_path, 999) == nf
    name = R.receipt_post(db, tmp_path, a, "image/jpeg", b"jpg")[1]["receipt"]
    (tmp_path / "receipts" / name).unlink()
    assert R.receipt_get(db, tmp_path, a) == nf
