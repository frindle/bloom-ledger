"""Frozen test: dashboard.html is a per-machine log view (machine selector, newest-first list of days)."""
import re
import subprocess
from pathlib import Path

from dom_support import find, rows, run_page, walk

HERE = Path(__file__).resolve().parent
SRC = (HERE / "dashboard.html").read_text()


def day(d, files, nbytes, state, h=None):
    return {"day": d, "files": files, "bytes": nbytes, "state": state, "chain_hash": h}


H1, H2 = "a1b2c3d4e5f60718" * 4, "ffeeddccbbaa9988" * 4
SUMMARY = {"generated_at": 1_000_000, "machines": [
    {"id": "alpha", "first_day": "2026-10-28", "last_seen": 999_000, "objects": {"ring": 5, "tokens": 2},
     "days": [day("2026-10-28", 3, 2048, "sealed", H1), day("2026-10-29", 0, 0, "missing"),
              day("2026-10-30", 4, 5, "open")]},
    {"id": "beta", "first_day": "2026-10-30", "last_seen": 990_000, "objects": {"ring": 1},
     "days": [day("2026-10-30", 1, 100, "sealed", H2)]}]}
FETCH = {"/v1/summary": {"status": 200, "body": SUMMARY},
         "/v1/alerts": {"status": 200, "body": [{"alert": "machine-silent", "machine_id": "beta", "age_s": 9000}]}}


def test_static_shape_and_wording():
    assert 'id="machine-select"' in SRC and 'id="day-rows"' in SRC and 'href="/settings"' in SRC and 'id="period-summary"' in SRC
    assert not re.search(r"chain.?hash|hash-toggle", SRC, re.I)
    assert not re.search(r"bitcoin|opentimestamps|\bots\b|timestamp", SRC, re.I)
    assert 'class="chain"' not in SRC and 'class: "day"' not in SRC
    assert "prefers-reduced-motion" in SRC and ":focus-visible" in SRC


def test_inline_script_parses(tmp_path):
    js = re.search(r"<script>(.*?)</script>", SRC, re.S).group(1)
    p = tmp_path / "s.js"
    p.write_text(js)
    r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]


def test_selector_and_newest_first_rows(tmp_path):
    res = run_page(tmp_path, FETCH, page="dashboard.html")
    assert res["errors"] == []
    sel = find(res["dom"], "machine-select")
    assert [o["text"].strip() for o in walk(sel) if o["tag"] == "option"] == ["alpha", "beta"]
    got = rows(res, "day-rows")
    assert [r[0] for r in got] == ["2026-10-30", "2026-10-29", "2026-10-28"]
    flat = [" | ".join(r) for r in got]
    assert "Open" in flat[0] and "Missing" in flat[1] and "Sealed" in flat[2]
    assert "3" in flat[2] and "2.0 KB" in flat[2]
    assert H1[:12] not in res["dom"]["text"] and len(got[2]) == 4
    assert "beta has sent nothing" in res["dom"]["text"]
    head = find(res["dom"], "machine-summary")["text"]
    assert "Last heard" in head and "1 day sealed" in head and "5 ring" in head


def test_switch_machine_remembers_choice(tmp_path):
    steps = [{"do": "change", "id": "machine-select", "values": {"machine-select": "beta"}}]
    res = run_page(tmp_path, FETCH, steps=steps, page="dashboard.html")
    assert res["errors"] == []
    assert [r[0] for r in rows(res, "day-rows")] == ["2026-10-30"]
    assert "beta" in res["session"].values()
    assert H2 not in res["dom"]["text"]


def test_unreachable_ledger_shows_banner(tmp_path):
    res = run_page(tmp_path, {"/v1/summary": {"network_error": True}, "/v1/alerts": {"network_error": True}},
                   page="dashboard.html")
    b = find(res["dom"], "banner")
    assert not b["hidden"] and "Can't reach the ledger" in b["text"]
