"""Frozen test (step 1): the home page links to the tax year and shows a labelled form for adding a purchase."""
import json
import os
import re
import subprocess
from pathlib import Path

import bloom_accounting_page as PG
from dom_support import find, walk

HERE = Path(__file__).resolve().parent
URL = "/v1/accounting/summary?period=month"
TOT = {"earned_micro": 1_000_000, "gpu_micro": 1_000_000, "sandbox_micro": 0, "gpu_cost_micro": 0, "sandbox_cost_micro": 0,
       "gpu_minutes": 1, "sandbox_minutes": 0, "other_minutes": 0, "tokens": 5, "wh": 10.0, "minutes": 60, "paid_minutes": 1,
       "cost_micro": 1000, "kwh": 0.01, "total_hours": 1.0, "paid_hours": 0.02, "business_bp": 166}
ENTRIES = [{"id": 7, "kind": "cost", "date": "2026-10-02", "amount_cents": 1999, "category": "software", "machine_id": None, "note": "tool", "voided": False},
           {"id": 8, "kind": "cost", "date": "2026-10-20", "amount_cents": 500, "category": "other", "machine_id": None, "note": None, "voided": True}]
SUM = {"totals": TOT, "net_micro": 1, "net_missing": [], "lease_cents": 0, "depreciation_business_cents": 0, "days": [],
       "entries": ENTRIES, "not_set": [], "power": {"basis": "metered", "estimated": False, "note": "grid"}}
FORM = {"e-date": "2026-11-02", "e-amount": "$1,249.5", "e-category": "hardware", "e-kind": "cost", "e-note": "  Studio stand  "}


def run(tmp_path, steps, extra=None):
    page = tmp_path / "home.html"
    page.write_text(PG.render_page())
    fetch = {URL: {"status": 200, "body": SUM}, "/v1/alerts": {"status": 200, "body": []}}
    fetch.update(extra or {})
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps({"fetch": fetch, "steps": steps}))
    res = subprocess.run(["node", str(HERE / "dom_harness.js"), str(page), str(sp)], capture_output=True, text=True, timeout=60,
                         env={k: v for k, v in os.environ.items() if k != "NODE_V8_COVERAGE"})
    assert res.returncode == 0 and res.stdout, res.stderr[-600:]
    out = json.loads(res.stdout)
    assert out["errors"] == [] and out["inner_html_writes"] == 0
    return out


def posts(res):
    return [f for f in res["fetches"] if f["method"] == "POST"]


def node(res, el_id):
    n = find(res["dom"], el_id)
    assert n is not None, "no #" + el_id + " on the page"
    return n


def msg(res):
    return node(res, "entry-msg")["text"]


def test_nav_links_to_tax_year():
    h = PG.body_html()
    assert '<a href="/log">Log</a> <a href="/tax">Tax year</a> <a href="/settings">Settings</a>' in h


def test_form_fields_are_labelled():
    h, css = PG.body_html(), PG.style_block()
    for i in ("entry-form", "e-date", "e-amount", "e-category", "e-kind", "e-note", "entry-msg"):
        assert 'id="%s"' % i in h, i
    for i in ("e-date", "e-amount", "e-category", "e-kind", "e-note"):
        assert '<label for="%s">' % i in h, i
    cats = re.findall(r'<option value="([^"]*)"', h[h.index('id="e-category"'):h.index('id="e-kind"')])
    assert sorted(cats) == ["electricity", "hardware", "interest", "internet", "other", "software", "supplies"]
    kinds = re.findall(r'<option value="([^"]*)"', h[h.index('id="e-kind"'):h.index('id="e-note"')])
    assert kinds == ["cost", "receipt"]
    assert 'role="status"' in h and '<button type="submit"' in h
    assert ".entry-form {" in css and "input:focus-visible" in css


def test_entries_table_has_action_column():
    h, css = PG.body_html(), PG.style_block()
    assert '<h2 id="entries-h">Purchases and other entries</h2>' in h
    assert '<th scope="col"><span class="sr">Action</span></th></tr></thead>' in h
    assert "A voided entry stays listed for the record but no longer counts." in h
    assert ".sr {" in css
