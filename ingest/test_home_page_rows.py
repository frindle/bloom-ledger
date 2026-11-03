"""Frozen test: the home page fills the per-day table and the entries list (voided entries marked)."""
import bloom_accounting_page as PG
from dom_support import find, rows
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

TOTALS = {"earned_micro": 3_500_000, "tokens": 300, "wh": 2500.0, "minutes": 150, "paid_minutes": 90, "cost_micro": 100_000,
          "kwh": 2.5, "total_hours": 2.5, "paid_hours": 1.5, "business_bp": 6000}
DAYS = [{"date": "2026-10-30", "earned_micro": 2_000_000, "tokens": 200, "wh": 1500.0, "minutes": 90, "paid_minutes": 60, "cost_micro": 60_000},
        {"date": "2026-10-29", "earned_micro": 1_500_000, "tokens": 100, "wh": 1000.0, "minutes": 60, "paid_minutes": 30, "cost_micro": 40_000}]
ENTRIES = [{"id": 1, "kind": "cost", "date": "2026-10-02", "amount_cents": 1999, "category": "software", "machine_id": None, "note": "tool", "voided": False},
           {"id": 2, "kind": "receipt", "date": "2026-10-20", "amount_cents": 500, "category": "other", "machine_id": "m4", "note": None, "voided": True}]
SUM = {"totals": TOTALS, "net_micro": 1, "net_missing": [], "days": DAYS, "entries": ENTRIES, "not_set": [],
       "power": {"basis": "metered", "estimated": False, "note": "grid rates, solar credit not applied"}}
FETCH = {"/v1/accounting/summary?period=month": {"status": 200, "body": SUM}}


def test_day_rows_newest_first_with_formatted_cells(tmp_path):
    assert "day-rows" in PG.script_js() and "day-rows" in PG.render_page()
    res = run_home(tmp_path, FETCH)
    assert res["errors"] == [] and res["inner_html_writes"] == 0
    assert rows(res, "day-rows") == [["2026-10-30", "$2.00", "$0.00", "$0.06", "1.5", "1.00", "1.50", "200"], ["2026-10-29", "$1.50", "$0.00", "$0.04", "1.0", "0.50", "1.00", "100"]]


def test_entries_newest_first_and_voided_marked(tmp_path):
    res = run_home(tmp_path, FETCH)
    got = rows(res, "entry-rows")
    assert got == [["2026-10-20", "receipt", "other", "$5.00", "m4", "", "Voided", ""],
                   ["2026-10-02", "cost", "software", "$19.99", "All", "tool", "Active", "Void"]]
    trs = [n for n in find(res["dom"], "entry-rows")["children"] if n["tag"] == "tr"]
    assert trs[0]["class"] == "voided" and trs[1]["class"] != "voided"
