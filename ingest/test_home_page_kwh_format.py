"""Frozen test: kWh formatter (exactly one decimal) and where the home page uses it."""
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


def test_formatter_boundaries():
    cases = [0, 8.592, 1.5, 10, 0.04, 1.25, 1234.56, -1, "NaN", "undefined", "Infinity"]
    got = node_values(PG.kwh_format_js(), [f"fmtKwh({c})" for c in cases])
    assert got == ["0.0", "8.6", "1.5", "10.0", "0.0", "1.3", "1234.6", "0.0", "0.0", "0.0", "0.0"]


def test_formatter_is_shipped_in_the_page_script():
    assert "function fmtKwh" in PG.script_js() and PG.render_page().count("<script>") == 1


def test_power_card_and_day_table_use_one_decimal(tmp_path):
    res = run_home(tmp_path, TOTALS, DAYS)
    assert card(res, "Power")["text"] == "8.6 kWh"
    assert [r[4] for r in day_cells(res)] == ["8.6", "1.5"]

