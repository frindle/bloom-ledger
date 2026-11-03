"""The days table opens a day: fetches its logs, draws the minute strip, payments and hourly table, and closes again."""
import json
import os
import subprocess
from pathlib import Path

import bloom_accounting_page as PG
from dom_support import find, walk

HERE = Path(__file__).resolve().parent
URL = "/v1/accounting/summary?period=month"
TOT = {"earned_micro": 3_000_000, "gpu_micro": 1_000_000, "sandbox_micro": 2_000_000, "gpu_cost_micro": 10_000,
       "sandbox_cost_micro": 30_000, "gpu_minutes": 20, "sandbox_minutes": 50, "other_minutes": 90, "tokens": 5, "wh": 300.0,
       "minutes": 1400, "paid_minutes": 70, "cost_micro": 90_000, "kwh": 0.3, "total_hours": 23.3, "paid_hours": 1.17, "business_bp": 500}
DAY = dict({k: v for k, v in TOT.items() if k not in ("kwh", "total_hours", "paid_hours", "business_bp")}, date="2026-11-02")
SUM = {"totals": TOT, "net_micro": 2_000_000, "net_missing": [], "days": [DAY], "entries": [], "not_set": [],
       "power": {"basis": "metered", "estimated": False, "note": "grid"}}
DETAIL = {"date": "2026-11-02", "tz": "America/Los_Angeles",
          "earnings": [{"ts": 1, "time": "20:08:04", "stream": "sandbox", "kind": "sandbox", "model": "sandbox:linux", "job_id": "sandbox:sbx_1",
                        "micro_usd": 2250, "tokens": 0}],
          "minutes": [{"ts": 1, "time": "20:08", "slot": 1208, "stream": "sandbox", "wh": 0.5, "cost_micro": 40, "tokens": 0, "sandbox_jobs": 1, "state": "serving"},
                      {"ts": 2, "time": "20:09", "slot": 1209, "stream": "idle", "wh": 0.4, "cost_micro": None, "tokens": 0, "sandbox_jobs": 0, "state": "serving"}],
          "hours": [{"hour": 20, "wh": 900.0, "cost_micro": 40, "earned_micro": 2250, "gpu_micro": 0, "sandbox_micro": 2250,
                     "gpu": 0, "sandbox": 1, "other": 0, "idle": 1, "gap": 0}]}
DURL = "/v1/accounting/day?date=2026-11-02"


def run(tmp_path, steps):
    page = tmp_path / "home.html"
    page.write_text(PG.render_page())
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps({"fetch": {URL: {"status": 200, "body": SUM}, DURL: {"status": 200, "body": DETAIL},
                                        "/v1/alerts": {"status": 200, "body": []}}, "steps": steps}))
    res = subprocess.run(["node", str(HERE / "dom_harness.js"), str(page), str(sp)], capture_output=True, text=True, timeout=60,
                         env={k: v for k, v in os.environ.items() if k != "NODE_V8_COVERAGE"})
    assert res.returncode == 0 and res.stdout, res.stderr[-600:]
    out = json.loads(res.stdout)
    assert out["errors"] == [] and out["inner_html_writes"] == 0
    return out


def test_streams_show_each_margin(tmp_path):
    text = find(run(tmp_path, [])["dom"], "streams")["text"]
    assert "Darkbloom GPU" in text and "$1.00" in text and "−$0.01" in text and "$0.99" in text
    assert "Sandbox" in text and "$2.00" in text and "−$0.03" in text and "$1.97" in text and "50 paid minutes" in text


def test_open_and_close_a_day(tmp_path):
    res = run(tmp_path, [{"do": "click", "sel": ".toggle"}])
    assert DURL in [f["url"] for f in res["fetches"]]
    rows = find(res["dom"], "day-rows")["children"]
    assert len(rows) == 2 and rows[1]["id"] == "day-2026-11-02"
    btn = [n for n in walk(rows[0]) if n["tag"] == "button"][0]
    assert btn["attrs"]["aria-expanded"] == "true" and btn["attrs"]["aria-controls"] == "day-2026-11-02"
    t = rows[1]["text"]
    assert "20:08:04" in t and "sandbox:sbx_1" in t and "$0.00225" in t and "20:00" in t and "Show all 2 minutes" in t
    segs = [n for n in walk(rows[1]) if "seg" in n["class"].split()]
    assert [n["class"] for n in segs] == ["seg s-none", "seg s-sandbox", "seg s-idle", "seg s-none"]
    res = run(tmp_path, [{"do": "click", "sel": ".toggle"}, {"do": "click", "sel": ".more"}])
    assert "Every power minute" in find(res["dom"], "day-rows")["text"]
    res = run(tmp_path, [{"do": "click", "sel": ".toggle"}, {"do": "click", "sel": ".toggle"}])
    assert len(find(res["dom"], "day-rows")["children"]) == 1
