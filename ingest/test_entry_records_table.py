"""Frozen test: the entries table shows who was paid, the purpose, the business-use percent and the receipt."""
import bloom_accounting_page as PG
from dom_support import walk
from test_home_page_entry_form import SUM, URL, node, run

ENTS = [{"id": 7, "kind": "cost", "date": "2026-10-02", "amount_cents": 1999, "category": "software", "machine_id": None, "note": None,
         "voided": False, "vendor": "Acme", "purpose": "Model hosting", "business_pct": 40, "receipt": "entry-7-ab.pdf"},
        {"id": 8, "kind": "cost", "date": "2026-10-03", "amount_cents": 500, "category": "supplies", "machine_id": None, "note": None,
         "voided": False, "vendor": None, "purpose": None, "business_pct": None, "receipt": None},
        {"id": 9, "kind": "receipt", "date": "2026-10-04", "amount_cents": 700, "category": "other", "machine_id": None, "note": None,
         "voided": False, "vendor": None, "purpose": None, "business_pct": 100, "receipt": None}]


def show(tmp_path):
    res = run(tmp_path, [], {URL: {"status": 200, "body": dict(SUM, entries=ENTS)}})
    rows = [n for n in node(res, "entry-rows")["children"] if n["tag"] == "tr"]
    return res, {r["children"][0]["text"]: [c["text"] for c in r["children"]] for r in rows}


def test_record_columns(tmp_path):
    assert '<th scope="col">Receipt</th>' in PG.body_html()
    res, by = show(tmp_path)
    heads = [n["text"] for n in walk(res["dom"]) if n["tag"] == "th"]
    for h in ("Paid to", "Purpose", "Business %", "Receipt"):
        assert h in heads, h
    assert by["2026-10-02"][6:10] == ["Acme", "Model hosting", "40%", "View"]
    assert by["2026-10-03"][6:10] == ["", "", "100%", "Missing"]
    assert by["2026-10-04"][6:10] == ["", "", "100%", ""]


def test_receipt_link(tmp_path):
    res, by = show(tmp_path)
    links = [n for n in walk(node(res, "entry-rows")) if n["tag"] == "a"]
    assert [(a["attrs"]["href"], a["text"]) for a in links] == [("/v1/accounting/entries/7/receipt", "View")]
    assert links[0]["attrs"]["aria-label"] == "View the receipt for the software entry from 2026-10-02"
