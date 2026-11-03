import importlib
import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
for _k in ("BLOOM_POWER_HOME", "BLOOM_QUEUE_STATE", "BLOOM_WORKER_METRICS"):
    os.environ.setdefault(_k, _tmp)
sys.path.insert(0, str(Path(__file__).resolve().parent / ".."))
lib = importlib.import_module("lib.bloom_power_lib")


def _e(day, usd_micro, model="gemma", job_id="job_1"):
    return {"created_at": f"2026-11-0{day}T01:00:00Z", "amount_micro_usd": usd_micro, "model": model, "job_id": job_id}


ENTRIES = [
    _e(2, 1_000_000, model="base_reward", job_id="floor:x"),
    _e(2, 500_000),
    _e(2, 2250, model="sandbox:linux-arm64-4cpu-16gb", job_id="sandbox:sbx_1"),
    _e(3, 2250, model="sandbox:linux-arm64-4cpu-16gb", job_id="sandbox:sbx_2"),
]


def test_totals_and_gross_include_sandbox():
    r = lib.summarize_earnings(ENTRIES)
    assert abs(r["sandbox"] - 0.0045) < 1e-9
    assert abs(r["base"] - 1.0) < 1e-9 and abs(r["job"] - 0.5) < 1e-9
    assert abs(r["gross"] - (r["base"] + r["job"] + r["sandbox"])) < 1e-9
    assert r["n"] == 4


def test_per_day_buckets():
    r = lib.summarize_earnings(ENTRIES)
    d2, d3 = r["by_day"]["2026-11-02"], r["by_day"]["2026-11-03"]
    assert abs(d2["sandbox"] - 0.00225) < 1e-9 and abs(d2["job"] - 0.5) < 1e-9 and d2["n"] == 3
    assert abs(d3["sandbox"] - 0.00225) < 1e-9 and d3["base"] == 0.0 and d3["job"] == 0.0


def test_without_sandbox_entries_unchanged():
    r = lib.summarize_earnings(ENTRIES[:2])
    assert r["sandbox"] == 0.0
    assert abs(r["gross"] - 1.5) < 1e-9


TESTS = [test_totals_and_gross_include_sandbox, test_per_day_buckets, test_without_sandbox_entries_unchanged]


if __name__ == "__main__":
    _bad = 0
    for _t in TESTS:
        try:
            _t()
            print(f"RESULT {_t.__name__} PASS")
        except Exception as _e:
            _bad += 1
            print(f"RESULT {_t.__name__} FAIL {type(_e).__name__}: {_e}")
    sys.exit(1 if _bad else 0)
