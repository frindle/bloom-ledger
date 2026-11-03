"""Frozen test: receipt upload and download routes on the real server. Fake data."""
import json

import bloom_accounting_receipts as RC
from server_fixture import web  # noqa: F401

H = {"Host": "ledger.test", "Origin": "http://ledger.test"}
ENTRY = json.dumps({"kind": "cost", "date": "2026-10-20", "amount_cents": 1234, "category": "software"}).encode()


def add(web):
    status, _, body = web("POST", "/v1/accounting/entries", ENTRY, headers=H)
    assert status == 201
    return json.loads(body)["id"]


def test_upload_and_download(web, tmp_path):
    eid = add(web)
    pdf = b"%PDF-1.4 " + b"r" * 6000
    status, ctype, body = web("POST", "/v1/accounting/entries/%d/receipt" % eid, pdf, headers=dict(H, **{"Content-Type": "application/pdf"}))
    assert (status, ctype) == (201, "application/json"), body
    name = json.loads(body)["receipt"]
    assert (tmp_path / "receipts" / name).read_bytes() == pdf
    assert json.loads(web("GET", "/v1/accounting/entries")[2])["entries"][0]["receipt"] == name
    assert web("GET", "/v1/accounting/entries/%d/receipt" % eid) == (200, "application/pdf", pdf)
    assert web("POST", "/v1/accounting/entries", b"x" * 5000, headers=H)[0] == 413
    assert web("POST", "/v1/accounting/entries/void", json.dumps({"id": eid}).encode(), headers=H)[0] == 200
    assert web("GET", "/v1/accounting/entries/%d/receipt" % eid) == (200, "application/pdf", pdf)


def test_refusals(web, tmp_path, monkeypatch):
    eid = add(web)
    png = dict(H, **{"Content-Type": "image/png"})
    path = "/v1/accounting/entries/%d/receipt" % eid
    assert web("POST", path, b"png", headers={"Content-Type": "image/png"})[0] == 403
    assert web("POST", path, b"<x>", headers=dict(H, **{"Content-Type": "text/html"}))[0] == 415
    monkeypatch.setattr(RC, "MAX_BYTES", 8000)
    assert web("POST", path, b"x" * 8001, headers=png)[0] == 413
    assert web("POST", "/v1/accounting/entries/999/receipt", b"png", headers=png)[0] == 404
    assert not (tmp_path / "receipts").exists()
    status, ctype, body = web("GET", path)
    assert (status, ctype, json.loads(body)) == (404, "application/json", {"error": "not found"})
    assert web("GET", "/v1/accounting/entries/0/receipt")[0] == 404
