import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / '..'))
idx = importlib.import_module('ingest.bloom_accounting_index')


def _line(**kw):
    e = {"_id": "1", "created_at": "2026-11-03T04:08:04.198222Z", "amount_micro_usd": 2250,
         "completion_tokens": 0, "model": "gemma-x", "job_id": "job_1"}
    e.update(kw)
    return json.dumps(e)


def test_sandbox_by_model_prefix():
    r = idx.parse_earnings_line(_line(model="sandbox:linux-arm64-4cpu-16gb", job_id="job_1"))
    assert r is not None and r["kind"] == "sandbox"
    assert r["micro_usd"] == 2250 and r["model"] == "sandbox:linux-arm64-4cpu-16gb"


def test_sandbox_by_job_id_prefix():
    r = idx.parse_earnings_line(_line(model="other", job_id="sandbox:sbx_ab52e7d6"))
    assert r is not None and r["kind"] == "sandbox"
    assert r["job_id"] == "sandbox:sbx_ab52e7d6"


def test_base_reward_stays_base():
    assert idx.parse_earnings_line(_line(model="base_reward", job_id="x"))["kind"] == "base"
    assert idx.parse_earnings_line(_line(model="m", job_id="floor:2026-11-03T03:40Z:machine:abc"))["kind"] == "base"


def test_ordinary_job_stays_job_and_bad_lines_rejected():
    assert idx.parse_earnings_line(_line())["kind"] == "job"
    assert idx.parse_earnings_line(_line(amount_micro_usd=-1)) is None
    assert idx.parse_earnings_line("not json") is None


TESTS = [test_sandbox_by_model_prefix, test_sandbox_by_job_id_prefix, test_base_reward_stays_base,
         test_ordinary_job_stays_job_and_bad_lines_rejected]
