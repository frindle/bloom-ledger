"""Frozen test: receipt upload. Fake data."""
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


def test_upload(tmp_path):
    db, a, b = make()
    code, obj = R.receipt_post(db, tmp_path, a, "application/pdf; charset=binary", PDF)
    name = "entry-%d-%s.pdf" % (a, hashlib.sha256(PDF).hexdigest()[:16])
    assert (code, obj) == (201, {"receipt": name})
    assert (tmp_path / "receipts" / name).read_bytes() == PDF
    assert [e["receipt"] for e in AE.current_entries(db)] == [name]
    assert [p.name for p in (tmp_path / "receipts").iterdir()] == [name]
    code, obj = R.receipt_post(db, tmp_path, a, "IMAGE/JPEG", b"jpg")
    assert code == 201 and obj["receipt"] == "entry-%d-%s.jpg" % (a, hashlib.sha256(b"jpg").hexdigest()[:16])
    assert [e["receipt"] for e in AE.current_entries(db)] == [obj["receipt"]]


def test_refusals(tmp_path):
    db, a, b = make()
    assert R.receipt_post(db, tmp_path, a, "text/html", b"<x>")[0] == 415
    assert R.receipt_post(db, tmp_path, a, None, PDF)[0] == 415
    assert R.receipt_post(db, tmp_path, a, "image/png", b"")[0] == 400
    assert R.receipt_post(db, tmp_path, a, "image/png", b"x" * (R.MAX_BYTES + 1))[0] == 413
    assert R.receipt_post(db, tmp_path, a, "image/png", b"x" * R.MAX_BYTES)[0] == 201
    db, a, b = make()
    t2 = tmp_path / "t2"
    assert R.receipt_post(db, t2, b, "image/png", b"png")[0] == 404
    assert R.receipt_post(db, t2, 999, "image/png", b"png")[0] == 404
    assert not t2.exists() or not any((t2 / "receipts").iterdir())
    assert [e["receipt"] for e in AE.all_entries(db)] == [None, None]
