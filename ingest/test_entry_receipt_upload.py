"""Frozen test: a receipt file chosen on the add-entry form uploads after the entry is created."""
import json

import bloom_accounting_page as PG
from dom_support import walk
from test_home_page_entry_form import FORM, SUM, URL, msg, node, posts, run

OK = {"POST /v1/accounting/entries": {"status": 201, "body": {"id": 9}}}
RCPT = "/v1/accounting/entries/9/receipt"
PDF = [{"name": "r.pdf", "type": "application/pdf", "body": "%PDF-1.4 fake"}]


def submit(tmp_path, values, files=None, extra=None):
    step = {"do": "submit", "id": "entry-form", "values": dict(FORM, **values)}
    if files:
        step["files"] = files
    return run(tmp_path, [step], dict(OK, **(extra or {})))


def labelled(res, i):
    return any(n.get("attrs", {}).get("for") == i for n in walk(node(res, "entry-form")))


def test_receipt_uploads_after_the_entry(tmp_path):
    assert 'id="e-receipt"' in PG.body_html()
    res = run(tmp_path, [])
    assert labelled(res, "e-receipt") and node(res, "e-receipt")["attrs"]["type"] == "file"
    assert "application/pdf" in node(res, "e-receipt")["attrs"]["accept"]
    res = submit(tmp_path, {}, {"e-receipt": PDF}, {"POST " + RCPT: {"status": 201, "body": {"receipt": "entry-9-x.pdf"}}})
    p = posts(res)
    assert [f["url"] for f in p] == ["/v1/accounting/entries", RCPT]
    assert p[1]["headers"]["content-type"] == "application/pdf" and p[1]["body"] == "%PDF-1.4 fake"
    assert msg(res).startswith("Added $1") and msg(res).endswith(", with the receipt.")
    assert [f["url"] for f in res["fetches"]].count(URL) == 2 and node(res, "e-receipt")["value"] == ""
    assert [f["url"] for f in posts(submit(tmp_path, {}))] == ["/v1/accounting/entries"]


def test_receipt_failures(tmp_path):
    res = submit(tmp_path, {}, {"e-receipt": PDF}, {"POST " + RCPT: {"status": 415, "body": {"error": "receipt must be a PDF, JPEG, PNG, HEIC or WebP file"}}})
    m = msg(res)
    assert m.startswith("Added $1") and "receipt was not saved (receipt must be a PDF, JPEG, PNG, HEIC or WebP file)" in m
    assert m.endswith("Void the entry and add it again with the receipt.")
    res = submit(tmp_path, {}, {"e-receipt": PDF}, {"POST " + RCPT: {"network_error": True}})
    assert "receipt was not saved (can't reach the ledger)" in msg(res)
    res = submit(tmp_path, {}, {"e-receipt": [dict(PDF[0], size=10485761)]})
    assert posts(res) == [] and msg(res) == "The receipt is over 10 MB. Nothing was added."
    res = submit(tmp_path, {}, {"e-receipt": [dict(PDF[0], size=10485760)]}, {"POST " + RCPT: {"status": 201, "body": {"receipt": "x"}}})
    assert len(posts(res)) == 2
