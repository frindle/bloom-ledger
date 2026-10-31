"""Frozen test: bloom_accounting_index.parse_earnings_line (synthetic rows)."""
import json

import bloom_accounting_index as A


def line(**kw):
    row = {"_id": "L1", "created_at": "2026-10-20T12:30:00Z", "amount_micro_usd": 1500, "model": "m-small",
           "job_id": "j1", "completion_tokens": 42}
    row.update(kw)
    return json.dumps(row)


def test_job_row_fields():
    r = A.parse_earnings_line(line())
    assert r == {"ledger_id": "L1", "ts": 1792499400, "micro_usd": 1500, "kind": "job", "model": "m-small",
                 "job_id": "j1", "completion_tokens": 42}


def test_base_rows_and_id_fallback():
    assert A.parse_earnings_line(line(model="base_reward", job_id=None))["kind"] == "base"
    assert A.parse_earnings_line(line(job_id="floor:7"))["kind"] == "base"
    r = A.parse_earnings_line(json.dumps({"id": "X9", "created_at": "2026-10-20T00:00:00+00:00", "amount_micro_usd": 0}))
    assert r["ledger_id"] == "X9" and r["completion_tokens"] == 0 and r["job_id"] is None


def test_bad_lines_give_none():
    for bad in ("not json", "[1]", "null", line(_id=""), line(_id=5), line(amount_micro_usd=-1), line(amount_micro_usd=1.5),
                line(amount_micro_usd=True), line(created_at="garbage"), line(created_at=None)):
        assert A.parse_earnings_line(bad) is None, bad
