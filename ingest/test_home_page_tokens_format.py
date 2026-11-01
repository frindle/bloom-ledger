"""Frozen test: token formatters (full comma form, compact M form) and where the home page uses them."""
import json
import os
import subprocess
from pathlib import Path

import bloom_accounting_page as PG
from dom_support import find

HERE = Path(__file__).resolve().parent
ENV = {k: v for k, v in os.environ.items() if k != "NODE_V8_COVERAGE"}
URL = "/v1/accounting/summary?period=month"


def run_home(tmp_path, totals, days):
    page = tmp_path / "home.html"
    page.write_text(PG.render_page())
    sc = tmp_path / "scenario.json"
    body = {"totals": totals, "net_micro": None, "net_missing": [], "days": days, "entries": [], "not_set": [],
            "power": {"basis": "metered", "estimated": False, "note": "grid rates, solar credit not applied"}}
    sc.write_text(json.dumps({"fetch": {URL: {"status": 200, "body": body}}, "steps": []}))
    res = subprocess.run(["node", str(HERE / "dom_harness.js"), str(page), str(sc)], capture_output=True, text=True, timeout=60, env=ENV)
    assert res.returncode == 0 and res.stdout, f"harness failed: {res.stderr[-600:]}"
    out = json.loads(res.stdout)
    assert out["errors"] == [] and out["inner_html_writes"] == 0
    return out


def card(res, label):
    for div in find(res["dom"], "summary")["children"]:
        kids = div["children"]
        if kids[0]["text"] == label:
            return kids[1]
    raise AssertionError("no card " + label)


def day_cells(res):
    return [[c["text"] for c in tr["children"]] for tr in find(res["dom"], "day-rows")["children"] if tr["tag"] == "tr"]


def node_values(js, exprs):
    code = js + "\nconsole.log(JSON.stringify([" + ",".join(exprs) + "]));"
    res = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=60, env=ENV)
    assert res.returncode == 0, res.stderr[-600:]
    return json.loads(res.stdout)


TOTALS = {"earned_micro": 1, "tokens": 31642663, "wh": 8592.0, "minutes": 300, "paid_minutes": 210, "cost_micro": 1, "kwh": 8.592,
          "total_hours": 5.0, "paid_hours": 3.5, "business_bp": 7000}
DAYS = [{"date": "2026-10-30", "earned_micro": 1, "tokens": 31642663, "wh": 8592.0, "minutes": 90, "paid_minutes": 60, "cost_micro": 1},
        {"date": "2026-10-29", "earned_micro": 1, "tokens": 999, "wh": 1500.0, "minutes": 60, "paid_minutes": 30, "cost_micro": 1}]


def test_formatters_boundaries():
    js = PG.tokens_format_js()
    cases = [0, 999, 1000, 999999, 1000000, 31642663, 1500, 12345, -5, "NaN", "undefined", "Infinity"]
    exprs = [f"fmtTokensCompact({c})" for c in cases] + [f"fmtTokensFull({c})" for c in cases]
    got = node_values(js, exprs)
    n = len(cases)
    assert got[:n] == ["0", "999", "1,000", "999,999", "1.0M", "31.6M", "1,500", "12,345", "0", "0", "0", "0"]
    assert got[n:] == ["0", "999", "1,000", "999,999", "1,000,000", "31,642,663", "1,500", "12,345", "0", "0", "0", "0"]


def test_formatters_are_shipped_in_the_page_script():
    assert "function fmtTokensCompact" in PG.script_js() and "function fmtTokensFull" in PG.script_js()
    assert PG.render_page().count("<script>") == 1


def test_summary_card_compact_with_full_title_and_day_table_full(tmp_path):
    res = run_home(tmp_path, TOTALS, DAYS)
    dd = card(res, "Tokens")
    assert dd["text"] == "31.6M" and dd["attrs"]["title"] == "31,642,663"
    assert [r[4] for r in day_cells(res)] == ["31,642,663", "999"]


def test_summary_card_small_counts(tmp_path):
    res = run_home(tmp_path, dict(TOTALS, tokens=1500), [])
    dd = card(res, "Tokens")
    assert dd["text"] == "1,500" and dd["attrs"]["title"] == "1,500"
