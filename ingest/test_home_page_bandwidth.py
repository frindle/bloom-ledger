"""Frozen test: the ledger page shows data moved (in/out bytes) per stream and for the whole machine. Fake data."""
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
       "minutes": 2846, "paid_minutes": 70, "cost_micro": 40_000, "kwh": 0.5, "total_hours": 47.43, "paid_hours": 1.17, "business_bp": 245,
       "gpu_bytes_in": 1_234_567_890, "gpu_bytes_out": 45_600, "sandbox_bytes_in": 999, "sandbox_bytes_out": 0,
       "total_bytes_in": 2_500_000_000_000, "total_bytes_out": 7_250_000, "net_minutes": 2800}
SUM = {"totals": TOT, "net_micro": 2_920_000, "net_missing": [], "lease_cents": 0, "depreciation_cents": 129,
       "depreciation_business_cents": 129, "days": [], "entries": [], "not_set": [],
       "power": {"basis": "metered", "estimated": False, "note": "grid"}}


def run(tmp_path, summ):
    page = tmp_path / "home.html"
    page.write_text(PG.render_page())
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps({"fetch": {URL: {"status": 200, "body": summ}, "/v1/alerts": {"status": 200, "body": []}}, "steps": []}))
    res = subprocess.run(["node", str(HERE / "dom_harness.js"), str(page), str(sp)], capture_output=True, text=True, timeout=60,
                         env={k: v for k, v in os.environ.items() if k != "NODE_V8_COVERAGE"})
    assert res.returncode == 0 and res.stdout, res.stderr[-600:]
    out = json.loads(res.stdout)
    assert out["errors"] == [], out["errors"]
    return out


def metas(dom):
    gpu, sbx = [n for n in walk(find(dom, "streams")) if n["tag"] == "article"]
    whole = [n for n in find(dom, "summary")["children"] if n["tag"] == "p"]
    assert len(whole) == 1, whole
    return gpu["text"], sbx["text"], whole[0]["text"]


def test_bytes_formatter_is_defined():
    js = PG.bytes_format_js()
    assert "function fmtBytes(n)" in js and js in PG.script_js()


def test_streams_and_machine_show_data_moved(tmp_path):
    gpu, sbx, whole = metas(run(tmp_path, SUM)["dom"])
    assert "data 1.2 GB in, 45.6 KB out" in gpu, gpu
    assert "data 999 B in, 0 B out" in sbx, sbx
    assert "data 2.5 TB in, 7.3 MB out" in whole, whole
    assert "11.0 h your own work, data 2.5 TB in" in whole and whole.endswith(", 155,085 tokens"), whole


def test_unmeasured_periods_say_so(tmp_path):
    for t in (dict(TOT, net_minutes=0), {k: v for k, v in TOT.items() if "bytes" not in k and k != "net_minutes"}):
        gpu, sbx, whole = metas(run(tmp_path, dict(SUM, totals=t))["dom"])
        assert all("data not measured" in x for x in (gpu, sbx, whole)), (gpu, sbx, whole)
        assert all(" B " not in x and " GB" not in x for x in (gpu, sbx, whole))


def test_large_units_cap_at_terabytes(tmp_path):
    gpu, _, _ = metas(run(tmp_path, dict(SUM, totals=dict(TOT, gpu_bytes_in=3_000_000_000_000_000)))["dom"])
    assert "data 3000.0 TB in" in gpu, gpu
