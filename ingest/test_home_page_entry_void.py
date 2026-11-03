"""Frozen test (step 2): each active entry row has a Void button that voids it and says why when refused."""
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


def test_void_button_on_active_rows_only(tmp_path):
    res = run(tmp_path, [])
    trs = [n for n in node(res, "entry-rows")["children"] if n["tag"] == "tr"]
    btns = [[n for n in walk(tr) if n["tag"] == "button"] for tr in trs]
    assert [len(b) for b in btns] == [0, 1], "newest first: the voided entry has no button"
    assert btns[1][0]["text"] == "Void" and btns[1][0]["attrs"]["aria-label"] == "Void the software entry from 2026-10-02"
    res = run(tmp_path, [{"do": "click", "sel": ".void"}], {"POST /v1/accounting/entries/void": {"status": 200, "body": {"ok": True}}})
    p = posts(res)
    assert len(p) == 1 and p[0]["url"] == "/v1/accounting/entries/void" and json.loads(p[0]["body"]) == {"id": 7}
    assert [f["url"] for f in res["fetches"]].count(URL) == 2 and msg(res) == "Entry voided."


def test_void_refusals_say_why(tmp_path):
    res = run(tmp_path, [{"do": "click", "sel": ".void"}], {"POST /v1/accounting/entries/void": {"status": 404, "body": {"error": "not found"}}})
    assert msg(res) == "Not saved: not found."
    assert [f["url"] for f in res["fetches"]].count(URL) == 1
    res = run(tmp_path, [{"do": "click", "sel": ".void"}], {"POST /v1/accounting/entries/void": {"status": 403, "body": {"error": "forbidden"}}})
    assert msg(res) == "Changes are only accepted from your local network."
