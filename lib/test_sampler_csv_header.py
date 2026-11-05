"""Frozen test (step 2): bloom_power_lib.csv_columns_for and appending rows to old/new month files.
Fixture ids only; no Darkbloom process, no network."""
import csv
import importlib.util
import json
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def load(name, file):
    sp = importlib.util.spec_from_file_location(name, HERE / file)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


L = load("bloom_power_lib_t", "bloom_power_lib.py")
OLD_COLUMNS = L.POWER_COLUMNS[:18]


def state(**over):
    d = {
        "pid": 4242,
        "written_at": time.time(),
        "started_at": 1793300000.25,
        "inference_active": False,
        "warm_models": ["fixture-model"],
        "trust": {"authorization": {"machine_id": "  fixture-machine-0001 ", "session_id": "s"}},
        "coordinator_connection": {"connected": True, "since": 1793300100.0, "connections": 3},
        "stats": {"requests_served": 12, "tokens_generated": 3456, "prompt_tokens_processed": 7890,
                  "cached_input_tokens": 5, "reasoning_tokens": 0, "usage_gaps": 2,
                  "cancellations_partial_complete": 1},
        "autopilot_state": {"resident_models": [{"model_id": "a", "resident_seconds": 100},
                                                {"model_id": "b", "resident_seconds": 23}]},
    }
    d.update(over)
    return d

def test_csv_columns_for(tmp_path):
    cols = list(L.POWER_COLUMNS)
    assert L.csv_columns_for(tmp_path / "missing.csv", cols) == cols
    old = tmp_path / "old.csv"
    old.write_text(",".join(OLD_COLUMNS) + "\n2026-10-13T10:00:00Z" + "," * 17 + "\n")
    assert L.csv_columns_for(old, cols) == OLD_COLUMNS
    new = tmp_path / "new.csv"
    new.write_text(",".join(cols) + "\n")
    assert L.csv_columns_for(new, cols) == cols
    torn = tmp_path / "torn.csv"
    torn.write_text("ts_utc,interval_s")
    assert L.csv_columns_for(torn, cols) == cols
    blank = tmp_path / "blank.csv"
    blank.write_text("\nrow\n")
    assert L.csv_columns_for(blank, cols) == cols
    odd = tmp_path / "odd.csv"
    odd.write_text("a,b,c\n")
    assert L.csv_columns_for(odd, cols) == ["a", "b", "c"], "the file's own header governs"


def row():
    r = {c: "" for c in L.POWER_COLUMNS}
    r.update({"ts_utc": "2026-10-30T01:00:00Z", "interval_s": 60, "samples": 60, "power_ok": 1, "avg_w": 10,
              "max_w": 12, "wh": 0.1667, "dbk_up": 1, "dbk_state": "idle", "inference_active_frac": 0.0,
              "requests_delta": 0, "tokens_delta": 0, "note": "a, b"})
    r.update(L.daemon_fields(state()))
    return r


def test_append_keeps_old_file_consistent(tmp_path):
    f = tmp_path / "power" / "power-log-2026-10.csv"
    f.parent.mkdir()
    f.write_text(",".join(OLD_COLUMNS) + "\n")
    L.append_csv_row(f, L.POWER_COLUMNS, row())
    recs = list(csv.reader(f.read_text().splitlines()))
    assert recs[0] == OLD_COLUMNS
    assert len(recs[1]) == len(OLD_COLUMNS), "a row appended to an old-header file must match that header"
    assert "fixture-machine-0001" not in f.read_text()


def test_append_new_file_has_all_columns(tmp_path):
    f = tmp_path / "power" / "power-log-2026-11.csv"
    L.append_csv_row(f, L.POWER_COLUMNS, row())
    L.append_csv_row(f, L.POWER_COLUMNS, row())
    rd = list(csv.DictReader(f.read_text().splitlines()))
    assert len(rd) == 2
    assert rd[1]["machine_id"] == "fixture-machine-0001"
    assert rd[1]["coordinator_connected"] == "1" and rd[1]["resident_seconds"] == "123"
    assert rd[0]["note"] == "a, b"


def test_main_header_has_no_sandbox_or_net_columns():
    assert "sandbox_jobs" not in L.POWER_COLUMNS and "gpu_bytes_in" not in L.POWER_COLUMNS
    assert L.POWER_COLUMNS[-1] == "resident_seconds" and len(L.POWER_COLUMNS) == 30
