"""Frozen test: the add-entry form sends who was paid, the business purpose and the business-use percent."""
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


def test_record_fields_sent(tmp_path):
    assert 'id="e-pct"' in PG.body_html()
    res = run(tmp_path, [])
    for i in ("e-vendor", "e-purpose", "e-pct"):
        assert labelled(res, i), "no label for #" + i
    assert node(res, "e-pct")["value"] == "100"
    res = submit(tmp_path, {"e-vendor": "  Apple Store ", "e-purpose": " Second node for inference ", "e-pct": " 60 "})
    p = posts(res)
    assert len(p) == 1 and p[0]["url"] == "/v1/accounting/entries"
    body = json.loads(p[0]["body"])
    assert (body["vendor"], body["purpose"], body["business_pct"]) == ("Apple Store", "Second node for inference", 60)
    assert node(res, "e-vendor")["value"] == "" and node(res, "e-purpose")["value"] == "" and node(res, "e-pct")["value"] == "100"
    assert msg(res).startswith("Added $1") and msg(res).endswith(".")
    body = json.loads(posts(submit(tmp_path, {"e-vendor": "   ", "e-purpose": "", "e-pct": ""}))[0]["body"])
    assert (body["vendor"], body["purpose"], body["business_pct"]) == (None, None, 100)


def test_bad_percent_not_sent(tmp_path):
    for bad in ("0", "101", "5.5", "abc", "-3", "1000"):
        res = submit(tmp_path, {"e-pct": bad})
        assert posts(res) == [] and msg(res) == "Enter the business-use percent as a whole number from 1 to 100.", bad
    assert json.loads(posts(submit(tmp_path, {"e-pct": "1"}))[0]["body"])["business_pct"] == 1
    assert json.loads(posts(submit(tmp_path, {"e-pct": "100"}))[0]["body"])["business_pct"] == 100
