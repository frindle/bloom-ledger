"""Frozen test: the home page script renders the five summary figures, with 'not set' links instead of zeros."""
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


def test_figures_render_with_values(tmp_path):
    res = run_home(tmp_path, {URL: {"status": 200, "body": SUM}})
    assert res["errors"] == [] and res["inner_html_writes"] == 0
    assert [f["url"] for f in res["fetches"] if f["url"].startswith("/v1/accounting/")][0] == URL
    text = summary_text(res)
    for want in ("$9.00", "1.5 kWh metered", "3.5 h paid of 5 h, 70% paid", "4,200"):
        assert want in text, want
    assert "not set" not in text and find(res["dom"], "banner")["hidden"]


def test_missing_inputs_say_not_set_with_settings_link(tmp_path):
    body = dict(SUM, net_micro=None, totals=dict(TOTALS, minutes=0, cost_micro=None, paid_minutes=0, business_bp=None, kwh=0.0))
    res = run_home(tmp_path, {URL: {"status": 200, "body": body}})
    assert res["errors"] == []
    links = [n for n in walk(find(res["dom"], "summary")) if n["tag"] == "a"]
    assert len(links) == 4 and all(n["attrs"]["href"] == "/settings" for n in links)
    assert summary_text(res).count("Set in Settings") >= 4
