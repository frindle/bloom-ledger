"""Frozen test: machine filter built from /v1/summary, refetch on change, and the power note (metered or estimated)."""
import bloom_accounting_page as PG
from dom_support import find, walk
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


TOTALS = {"earned_micro": 1, "tokens": 1, "wh": 0.0, "minutes": 60, "paid_minutes": 30, "cost_micro": 1, "kwh": 0.0, "total_hours": 1.0,
          "paid_hours": 0.5, "business_bp": 5000}


def summary(basis, estimated=False):
    return {"totals": TOTALS, "net_micro": 1, "net_missing": [], "days": [], "entries": [], "not_set": [],
            "power": {"basis": basis, "estimated": estimated, "note": "grid rates, solar credit not applied"}}


MACHINES = {"/v1/summary": {"status": 200, "body": {"generated_at": 1, "machines": [{"id": "alpha"}, {"id": "beta"}]}}}


def test_machine_filter_options_and_refetch(tmp_path):
    base = "/v1/accounting/summary?period=month"
    fetch = {**MACHINES, base: {"status": 200, "body": summary("metered")}, base + "&machine=beta": {"status": 200, "body": summary("metered")}}
    steps = [{"do": "change", "id": "machine", "values": {"machine": "beta"}}]
    res = run_home(tmp_path, fetch, steps)
    assert res["errors"] == [] and res["inner_html_writes"] == 0
    opts = [(o["attrs"].get("value", ""), o["text"].strip()) for o in walk(find(res["dom"], "machine")) if o["tag"] == "option"]
    assert opts == [("", "All machines"), ("alpha", "alpha"), ("beta", "beta")]
    urls = [f["url"] for f in res["fetches"]]
    assert base in urls and base + "&machine=beta" in urls and "/v1/summary" in urls


def test_power_note_says_metered_or_estimated(tmp_path):
    url = "/v1/accounting/summary?period=month"
    for body, want in ((summary("metered"), "Power is metered; grid rates, solar credit not applied."),
                       (summary("none", True), "Power is estimated from watts; grid rates, solar credit not applied."),
                       (summary("none"), "No power readings in this period; grid rates, solar credit not applied.")):
        res = run_home(tmp_path, {**MACHINES, url: {"status": 200, "body": body}})
        assert find(res["dom"], "power-note")["text"].strip() == want
    res = run_home(tmp_path, {"/v1/summary": {"network_error": True}, url: {"status": 200, "body": summary("metered")}})
    assert res["errors"] == [] and "Power is metered" in find(res["dom"], "power-note")["text"]
