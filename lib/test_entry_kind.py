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


def test_sandbox_by_model_prefix():
    assert lib.entry_kind({"model": "sandbox:linux-arm64-4cpu-16gb", "job_id": "x"}) == "sandbox"


def test_sandbox_by_job_id_prefix():
    assert lib.entry_kind({"model": "m", "job_id": "sandbox:sbx_1"}) == "sandbox"


def test_base_entries_stay_base():
    assert lib.entry_kind({"model": "base_reward"}) == "base"
    assert lib.entry_kind({"job_id": "floor:2026-11-03T03:40Z:machine:x"}) == "base"


def test_ordinary_and_empty_stay_job():
    assert lib.entry_kind({"model": "gemma", "job_id": "job_1"}) == "job"
    assert lib.entry_kind({}) == "job"


TESTS = [test_sandbox_by_model_prefix, test_sandbox_by_job_id_prefix, test_base_entries_stay_base,
         test_ordinary_and_empty_stay_job]
