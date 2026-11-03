"""Frozen test: bloom_accounting_index.power_columns / parse_power_line (synthetic rows)."""
import bloom_accounting_index as A

HDR = "ts_utc,interval_s,samples,power_ok,avg_w,max_w,wh,dbk_up,dbk_state,inference_active_frac,requests_delta,tokens_delta," \
      "warm_models,load_transition_active,gpu_pct,other_work,other_procs,note"


def row(ts="2026-10-20T12:00:00Z", ok="1", wh="2.5", other="0", toks="40"):
    return f"{ts},60,60,{ok},150,200,{wh},1,serving,0.5,1,{toks},m,0,50,{other},,"


def test_header_detection():
    assert A.power_columns(HDR + "\n") == A.LEGACY_POWER_COLUMNS
    assert A.power_columns(row()) is None and A.power_columns("a,b,c") is None and A.power_columns("") is None


def test_parse_row():
    r = A.parse_power_line(row(), A.LEGACY_POWER_COLUMNS)
    assert r == {"ts": 1792497600, "wh": 2.5, "interval_s": 60.0, "power_ok": 1, "dbk_state": "serving", "other_work": 0,
                 "tokens_delta": 40, "sandbox_jobs": 0, "active_frac": 0.5,
                 **{c: None for c in A.NET_COLUMNS}}
    assert A.parse_power_line(row(other="1", toks="7.0") + "\n", A.LEGACY_POWER_COLUMNS)["other_work"] == 1


def test_power_not_ok_and_bad_rows():
    r = A.parse_power_line(row(ok="0", wh="9.9"), A.LEGACY_POWER_COLUMNS)
    assert r["power_ok"] == 0 and r["wh"] == 0.0
    assert A.parse_power_line(row(ok="True", wh=""), A.LEGACY_POWER_COLUMNS)["wh"] == 0.0
    for bad in ("", "a,b", row(ts="garbage"), row(wh="x")):
        assert A.parse_power_line(bad, A.LEGACY_POWER_COLUMNS) is None, bad


def test_sandbox_jobs_column():
    cols = A.LEGACY_POWER_COLUMNS + ["sandbox_jobs"]
    assert A.parse_power_line(row() + ",2", cols)["sandbox_jobs"] == 2
    assert A.parse_power_line(row() + ",", cols)["sandbox_jobs"] == 0
    assert A.parse_power_line(row(), A.LEGACY_POWER_COLUMNS)["sandbox_jobs"] == 0
