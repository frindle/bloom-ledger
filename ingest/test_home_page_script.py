"""Frozen test: the home page script fetches the summary and renders the figures, with 'not set' links instead of zeros."""
import json

import bloom_accounting_page as PG
from dom_support import find, walk
from page_support import run_home

TOTALS = {"earned_micro": 12_340_000, "tokens": 4200, "wh": 1500.0, "minutes": 300, "paid_minutes": 210, "cost_micro": 250_000,
          "kwh": 1.5, "total_hours": 5.0, "paid_hours": 3.5, "business_bp": 7000}
SUM = {"totals": TOTALS, "net_micro": 9_000_000, "net_missing": [], "days": [], "entries": [], "not_set": [],
       "power": {"basis": "metered", "estimated": False, "note": "grid rates, solar credit not applied"}}
URL = "/v1/accounting/summary?period=month"


def summary_text(res):
    return find(res["dom"], "summary")["text"]


def test_document_and_script_shape():
    doc = PG.render_page()
    assert doc.startswith("<!doctype html>") and '<html lang="en">' in doc and "<title>Ledger</title>" in doc
    assert doc.count("<script>") == 1 and "<style>" in doc and 'id="summary"' in doc
    js = PG.script_js()
    assert "innerHTML" not in js and "http://" not in js and "https://" not in js and "/v1/accounting/summary" in js


def test_figures_render_with_values(tmp_path):
    res = run_home(tmp_path, {URL: {"status": 200, "body": SUM}})
    assert res["errors"] == [] and res["inner_html_writes"] == 0
    assert [f["url"] for f in res["fetches"]][0] == URL
    text = summary_text(res)
    for want in ("$12.34", "1.5 kWh", "cost $0.25", "3.5 h", "of 5.0 h, 70% business", "4200", "$9.00"):
        assert want in text, want
    assert "not set" not in text and find(res["dom"], "banner")["hidden"]


def test_missing_inputs_say_not_set_with_settings_link(tmp_path):
    body = dict(SUM, net_micro=None, totals=dict(TOTALS, minutes=0, cost_micro=None, paid_minutes=0, business_bp=None, kwh=0.0))
    res = run_home(tmp_path, {URL: {"status": 200, "body": body}})
    assert res["errors"] == []
    links = [n for n in walk(find(res["dom"], "summary")) if n["tag"] == "a"]
    assert len(links) == 3 and all(n["attrs"]["href"] == "/settings" for n in links)
    assert summary_text(res).count("not set") >= 3 and "cost not set" in summary_text(res)


def test_unreachable_shows_banner(tmp_path):
    res = run_home(tmp_path, {URL: {"network_error": True}})
    assert res["errors"] == [] and not find(res["dom"], "banner")["hidden"]
    res = run_home(tmp_path, {URL: {"status": 500, "body": {}}})
    assert not find(res["dom"], "banner")["hidden"]
