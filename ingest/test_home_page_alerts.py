"""Frozen test: the main page lists open alerts."""
import bloom_accounting_page as PG
from dom_support import find, texts
import json
import os
import subprocess
from pathlib import Path

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


URL = "/v1/accounting/summary?period=month"
SUM = {"totals": {"earned_micro": 1, "tokens": 1, "wh": 0.0, "minutes": 0, "paid_minutes": 0, "cost_micro": None, "kwh": 0.0,
                  "total_hours": 0.0, "paid_hours": 0.0, "business_bp": None},
       "net_micro": None, "net_missing": [], "days": [], "entries": [], "not_set": [],
       "power": {"basis": "none", "estimated": False, "note": "grid rates, solar credit not applied"}}


def test_alerts_listed(tmp_path):
    alerts = [{"alert": "machine-silent", "machine_id": "beta", "age_s": 9000},
              {"alert": "ring-snapshot-stale", "machine_id": "alpha", "age_s": 50000}, {"alert": "odd", "machine_id": "gamma"}]
    res = run_home(tmp_path, {URL: {"status": 200, "body": SUM}, "/v1/alerts": {"status": 200, "body": alerts}})
    assert res["errors"] == [] and res["inner_html_writes"] == 0
    assert texts(find(res["dom"], "alerts"), "li") == ["beta has sent nothing for 150 minutes.", "alpha has an old ring snapshot.", "gamma: odd"]


def test_no_alerts_and_failed_fetch(tmp_path):
    res = run_home(tmp_path, {URL: {"status": 200, "body": SUM}, "/v1/alerts": {"status": 200, "body": []}})
    assert texts(find(res["dom"], "alerts"), "li") == ["No open alerts."]
    res = run_home(tmp_path, {URL: {"status": 200, "body": SUM}, "/v1/alerts": {"network_error": True}})
    assert res["errors"] == [] and texts(find(res["dom"], "alerts"), "li") == []
    assert "/v1/alerts" in PG.script_js()
