"""Frozen test: bloom_accounting_receipts stores and serves one receipt file per ledger entry. Fake data."""
import hashlib
import importlib
import sqlite3

import bloom_accounting_entries as AE

PDF = b"%PDF-1.4 fake receipt\n"


def mod():
    try:
        return importlib.import_module("bloom_accounting_receipts")
    except ImportError:
        raise AssertionError("bloom_accounting_receipts is missing")


def make():
    db = sqlite3.connect(":memory:")
    a = AE.add_entry(db, {"kind": "cost", "date": "2026-10-05", "amount_cents": 1200, "category": "software"}, 1)
    b = AE.add_entry(db, {"kind": "cost", "date": "2026-10-06", "amount_cents": 300, "category": "supplies"}, 1)
    AE.void_entry(db, b, 2)
    return db, a, b


def test_paths_and_upload(tmp_path):
    R = mod()
    assert R.entry_id_from_path("/v1/accounting/entries/12/receipt") == 12
    assert R.entry_id_from_path("/v1/accounting/entries/12/receipt?x=1") == 12
    for bad in ("/v1/accounting/entries/0/receipt", "/v1/accounting/entries/-1/receipt", "/v1/accounting/entries/x/receipt",
                "/v1/accounting/entries/12/receipt/..", "/v1/accounting/entries/12", "/v1/accounting/entries/void"):
        assert R.entry_id_from_path(bad) is None, bad
    db, a, b = make()
    code, obj = R.receipt_post(db, tmp_path, a, "application/pdf; charset=binary", PDF)
    name = "entry-%d-%s.pdf" % (a, hashlib.sha256(PDF).hexdigest()[:16])
    assert (code, obj) == (201, {"receipt": name})
    assert (tmp_path / "receipts" / name).read_bytes() == PDF
    assert [e["receipt"] for e in AE.current_entries(db)] == [name]
    assert [p.name for p in (tmp_path / "receipts").iterdir()] == [name]
    assert R.receipt_get(db, tmp_path, a) == (200, "application/pdf", PDF)


def test_refusals(tmp_path):
    R = mod()
    db, a, b = make()
    assert R.receipt_post(db, tmp_path, a, "text/html", b"<x>")[0] == 415
    assert R.receipt_post(db, tmp_path, a, None, PDF)[0] == 415
    assert R.receipt_post(db, tmp_path, a, "image/png", b"")[0] == 400
    assert R.receipt_post(db, tmp_path, a, "image/png", b"x" * (R.MAX_BYTES + 1))[0] == 413
    assert R.receipt_post(db, tmp_path, b, "image/png", b"png")[0] == 404
    assert R.receipt_post(db, tmp_path, 999, "image/png", b"png")[0] == 404
    assert not (tmp_path / "receipts").exists() or not any((tmp_path / "receipts").iterdir())
    assert R.receipt_get(db, tmp_path, a)[0] == 404 and R.receipt_get(db, tmp_path, 999)[0] == 404
    code, obj = R.receipt_post(db, tmp_path, a, "IMAGE/JPEG", b"jpg")
    assert code == 201 and obj["receipt"].endswith(".jpg")
    assert R.receipt_get(db, tmp_path, a) == (200, "image/jpeg", b"jpg")
    (tmp_path / "receipts" / obj["receipt"]).unlink()
    assert R.receipt_get(db, tmp_path, a)[0] == 404
