"""Frozen test: the home page document has one inline script that fetches the summary and shows the banner when the ledger is unreachable."""
import json
import os
import subprocess
from pathlib import Path

import bloom_accounting_page as PG
from dom_support import find, walk

HERE = Path(__file__).resolve().parent


def run_home(tmp_path, fetch, steps=None):
    page = tmp_path / "home.html"
    page.write_text(PG.render_page())
    sp = tmp_path / "scenario.json"
    sp.write_text(json.dumps({"fetch": fetch, "steps": steps or []}))
    res = subprocess.run(["node", str(HERE / "dom_harness.js"), str(page), str(sp)], capture_output=True, text=True, timeout=60,
                         env={k: v for k, v in os.environ.items() if k != "NODE_V8_COVERAGE"})
    assert res.returncode == 0 and res.stdout, f"harness failed: {res.stderr[-600:]}"
    return json.loads(res.stdout)


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
    assert '$("#' not in js and "$('#" not in js, 'script_js: $ takes a bare id, write $("period"), never $("#period")'


def test_unreachable_shows_banner(tmp_path):
    res = run_home(tmp_path, {URL: {"network_error": True}})
    assert res["errors"] == [] and not find(res["dom"], "banner")["hidden"]
    res = run_home(tmp_path, {URL: {"status": 500, "body": {}}})
    assert not find(res["dom"], "banner")["hidden"]
