"""Frozen test: sub-cent stream power shows its real size, and the whole-machine box reconciles the stream margins to Net."""
import json
import os
import subprocess
from pathlib import Path

import bloom_accounting_page as PG
from dom_support import find, walk

HERE = Path(__file__).resolve().parent
URL = "/v1/accounting/summary?period=month"
TOT = {"earned_micro": 4_250_000, "gpu_micro": 1_180_000, "sandbox_micro": 3_070_000, "gpu_cost_micro": 2_300,
       "sandbox_cost_micro": 2_900, "gpu_minutes": 20, "sandbox_minutes": 50, "other_minutes": 660, "tokens": 155_085, "wh": 500.0,
       "minutes": 2846, "paid_minutes": 70, "cost_micro": 40_000, "kwh": 0.5, "total_hours": 47.43, "paid_hours": 1.17, "business_bp": 245}
SUM = {"totals": TOT, "net_micro": 2_920_000, "net_missing": [], "lease_cents": 0, "depreciation_cents": 129,
       "depreciation_business_cents": 129, "days": [], "entries": [], "not_set": [],
       "power": {"basis": "metered", "estimated": False, "note": "grid"}}
LABELS = ["Darkbloom GPU margin", "Sandbox margin", "Power while idle or doing your own work", "Lease",
          "Depreciation (business share)", "Net"]


def run(tmp_path, summ):
    page = tmp_path / "home.html"
    page.write_text(PG.render_page())
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps({"fetch": {URL: {"status": 200, "body": summ}, "/v1/alerts": {"status": 200, "body": []}}, "steps": []}))
    res = subprocess.run(["node", str(HERE / "dom_harness.js"), str(page), str(sp)], capture_output=True, text=True, timeout=60,
                         env={k: v for k, v in os.environ.items() if k != "NODE_V8_COVERAGE"})
    assert res.returncode == 0 and res.stdout, res.stderr[-600:]
    out = json.loads(res.stdout)
    assert out["errors"] == [] and out["inner_html_writes"] == 0
    return out


def tags(node, tag):
    return [n for n in walk(node) if n["tag"] == tag]


def cards(dom):
    return [n for n in walk(find(dom, "streams")) if n["tag"] == "article"]


def test_stream_power_shows_sub_cent_cost(tmp_path):
    gpu, sbx = cards(run(tmp_path, SUM)["dom"])
    assert "−$0.0023" in gpu["text"] and "$1.18" in gpu["text"]
    assert "−$0.0029" in sbx["text"] and "$3.07" in sbx["text"]
    assert all(dd["text"] != "−$0.00" for c in (gpu, sbx) for dd in tags(c, "dd"))


def test_summary_reconciles_margins_to_net(tmp_path):
    s = find(run(tmp_path, SUM)["dom"], "summary")
    assert [n["text"] for n in tags(s, "dt")] == LABELS
    assert [n["text"] for n in tags(s, "dd")] == ["$1.18", "$3.07", "−$0.03", "$0.00", "−$1.29", "$2.92"]
    total = [n for n in walk(s) if "total" in n["class"].split()]
    assert len(total) == 1 and "Net" in total[0]["text"]
    meta = [n for n in s["children"] if n["tag"] == "p"]
    assert len(meta) == 1 and "meta" in meta[0]["class"].split()
    t = meta[0]["text"]
    assert "0.5 kWh metered" in t and "1.17 h paid of 47.43 h, 2.45% paid" in t and "11.0 h your own work" in t
    span = tags(meta[0], "span")
    assert span and span[-1]["text"] == "155,085 tokens" and span[-1]["attrs"]["title"] == "155,085"


def test_unknown_costs_say_not_set(tmp_path):
    summ = dict(SUM, totals=dict(TOT, cost_micro=None), net_micro=None, depreciation_business_cents=None)
    s = find(run(tmp_path, summ)["dom"], "summary")
    dds = tags(s, "dd")
    for i in (0, 1, 2, 4, 5):
        assert "$" not in dds[i]["text"], (LABELS[i], dds[i]["text"])
        assert [a["attrs"]["href"] for a in tags(dds[i], "a")] == ["/settings"]
    assert dds[3]["text"] == "$0.00"

