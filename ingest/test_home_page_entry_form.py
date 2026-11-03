"""Frozen test (step 3): the add-entry form posts a purchase (write-off) and reloads, without leaving the page."""
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


def test_add_purchase_posts_entry_and_reloads(tmp_path):
    res = run(tmp_path, [{"do": "submit", "id": "entry-form", "values": FORM}],
              {"POST /v1/accounting/entries": {"status": 201, "body": {"id": 9}}})
    p = posts(res)
    assert len(p) == 1 and p[0]["url"] == "/v1/accounting/entries"
    assert p[0]["headers"]["content-type"] == "application/json"
    assert json.loads(p[0]["body"]) == {"kind": "cost", "date": "2026-11-02", "amount_cents": 124950, "category": "hardware",
                                        "machine_id": None, "note": "Studio stand"}
    assert [f["url"] for f in res["fetches"]].count(URL) == 2, "summary reloads after the add"
    m = msg(res)
    assert m.startswith("Added $1") and "124950" not in m and "hardware" in m and "2026-11-02" in m
    assert node(res, "e-amount")["value"] == "" and node(res, "e-note")["value"] == ""
    vals = dict(FORM, **{"e-amount": "12", "e-note": "   ", "e-category": "internet", "e-kind": "receipt", "machine": "m4"})
    res = run(tmp_path, [{"do": "submit", "id": "entry-form", "values": vals}],
              {"POST /v1/accounting/entries": {"status": 201, "body": {"id": 9}}})
    p = posts(res)
    assert len(p) == 1, "the form posts once"
    body = json.loads(p[0]["body"])
    assert body["amount_cents"] == 1200 and body["note"] is None and body["machine_id"] == "m4" and body["kind"] == "receipt"


def test_bad_input_is_not_sent(tmp_path):
    for amount in ("12.345", "0", "abc", "", "-5", "1.2.3"):
        res = run(tmp_path, [{"do": "submit", "id": "entry-form", "values": dict(FORM, **{"e-amount": amount})}])
        assert posts(res) == [] and msg(res) == "Enter the amount in dollars, like 49.99.", amount
    res = run(tmp_path, [{"do": "submit", "id": "entry-form", "values": dict(FORM, **{"e-date": ""})}])
    assert posts(res) == [] and msg(res) == "Pick the date you paid."
    res = run(tmp_path, [{"do": "submit", "id": "entry-form", "values": dict(FORM, **{"e-amount": "0.07"})}],
              {"POST /v1/accounting/entries": {"status": 201, "body": {"id": 9}}})
    p = posts(res)
    assert len(p) == 1 and json.loads(p[0]["body"])["amount_cents"] == 7


def test_refusals_say_why(tmp_path):
    res = run(tmp_path, [{"do": "submit", "id": "entry-form", "values": FORM}],
              {"POST /v1/accounting/entries": {"status": 403, "body": {"error": "forbidden"}}})
    assert msg(res) == "Changes are only accepted from your local network."
    assert [f["url"] for f in res["fetches"]].count(URL) == 1
    res = run(tmp_path, [{"do": "submit", "id": "entry-form", "values": FORM}],
              {"POST /v1/accounting/entries": {"status": 400, "body": {"error": "bad category"}}})
    assert msg(res) == "Not saved: bad category."
    assert node(res, "e-amount")["value"] == "$1,249.5", "a refused entry keeps what was typed"


def test_date_defaults_to_today(tmp_path):
    res = run(tmp_path, [])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", node(res, "e-date")["value"])
