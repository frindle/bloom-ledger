"""Darkbloom API spend: ingest (mocked HTTP), the contribution entry kind, the tally's account block and the reconcile line.
Fake keys and made-up numbers."""
import datetime as dt
import json
import os
import sqlite3

import bloom_accounting_config as CF
import bloom_accounting_entries as AE
import bloom_accounting_index as AX
import bloom_accounting_live as LV
import bloom_accounting_summary as AS
import bloom_accounting_tally as TL
import bloom_api_spend as SP

KEY = "dbk_spend_0123456789abcdef"
T0 = int(dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc).timestamp())


def make(tmp_path, start=T0 - 10, key=KEY, monkeypatch=None):
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    root = tmp_path / "data"
    if key:
        LV._write_private(LV.key_path(root), key)
    if start is not None:
        CF.set_setting(db, "api_spend_from_ts", start, "2026-01-01", 1)
    return db, root


def row(rid, ts, cost, model="m1", p=10, c=5):
    return {"request_id": rid, "model": model, "prompt_tokens": p, "completion_tokens": c, "cost_micro_usd": cost, "timestamp": ts}


def getter(code, body, calls=None):
    def get(url, key):
        if calls is not None:
            calls.append((url, key))
        return code, body
    return get


def ids(db):
    return [r[0] for r in db.execute("SELECT request_id FROM api_spend ORDER BY ts DESC, request_id")]


def test_ingest_stores_dedupes_and_stops_at_known_rows(tmp_path):
    db, root = make(tmp_path)
    calls = []
    body = [row("r3", T0 + 30, 3000), row("r2", T0 + 20, 2000), row("r1", T0 + 10, 1000)]
    res = SP.ingest(db, root, T0 + 100, get=getter(200, body, calls))
    assert res == {"state": "ok", "http": 200, "added": 3} and ids(db) == ["r3", "r2", "r1"]
    assert calls == [(SP.USAGE_URL, KEY)]
    # a second pass with one new row on top stops at the first stored row: a changed older row is not re-read
    body2 = [row("r4", T0 + 40, 4000), row("r3", T0 + 30, 3000), row("r2", T0 + 20, 999999)]
    assert SP.ingest(db, root, T0 + 200, get=getter(200, body2))["added"] == 1
    assert db.execute("SELECT cost_micro_usd FROM api_spend WHERE request_id='r2'").fetchone()[0] == 2000
    # same response again adds nothing
    assert SP.ingest(db, root, T0 + 300, get=getter(200, body2))["added"] == 0 and len(ids(db)) == 4


def test_primary_key_blocks_duplicates_inside_one_response(tmp_path):
    db, root = make(tmp_path)
    body = [row("a", T0 + 5, 10), row("a", T0 + 4, 10)]
    assert SP.ingest(db, root, T0 + 9, get=getter(200, {"usage": body}))["added"] == 1


def test_ingest_from_ts_keeps_only_newer_rows(tmp_path):
    db, root = make(tmp_path, start=T0 + 15)
    body = [row("new", T0 + 30, 1), row("edge", T0 + 15, 2), row("old", T0 + 14, 3), row("older", T0 + 1, 4)]
    assert SP.ingest(db, root, T0 + 99, get=getter(200, body))["added"] == 2
    assert ids(db) == ["new", "edge"]


def test_no_start_setting_or_no_key_means_no_request(tmp_path, monkeypatch):
    monkeypatch.delenv("BLOOM_API_SPEND_FROM_TS", raising=False)
    calls = []
    db, root = make(tmp_path, start=None)
    assert SP.ingest(db, root, T0, get=getter(200, [], calls))["state"] == "no_start" and calls == []
    db, root = make(tmp_path / "nokey", key=None)
    assert SP.ingest(db, root, T0, get=getter(200, [], calls))["state"] == "no_key" and calls == []
    monkeypatch.setenv("BLOOM_API_SPEND_FROM_TS", str(T0))
    db, root = make(tmp_path / "env", start=None)
    assert SP.ingest(db, root, T0, get=getter(200, [row("e", T0 + 1, 5)], calls))["added"] == 1 and len(calls) == 1


def test_401_and_403_are_skipped_and_shown_in_the_key_status(tmp_path):
    db, root = make(tmp_path)
    for code in (401, 403):
        res = SP.ingest(db, root, T0 + 5, get=getter(code, None))
        assert res["state"] == "no_scope" and res["added"] == 0
        st = LV.key_status(root)
        assert st["api_spend"]["state"] == "no_scope" and st["api_spend"]["http"] == code
    SP.create_table(db)
    assert ids(db) == []
    assert SP.ingest(db, root, T0 + 6, get=getter(0, None))["state"] == "unreachable"
    assert SP.ingest(db, root, T0 + 7, get=getter(200, "nope"))["state"] == "bad_response"


def test_bad_rows_are_skipped(tmp_path):
    db, root = make(tmp_path)
    body = [row("../x", T0 + 9, 1), row("neg", T0 + 8, -5), {"request_id": "nots", "cost_micro_usd": 3},
            row("iso", "2026-11-10T12:00:20Z", 7), row("ms", (T0 + 7) * 1000, 8)]
    assert SP.ingest(db, root, T0 + 50, get=getter(200, body))["added"] == 2
    assert dict(db.execute("SELECT request_id, ts FROM api_spend")) == {"iso": T0 + 20, "ms": T0 + 7}


def test_the_key_never_reaches_the_log_status_or_the_database(tmp_path, capsys):
    db, root = make(tmp_path)
    SP.ingest(db, root, T0 + 5, get=getter(200, [row("r1", T0 + 1, 1)]))
    SP.ingest(db, root, T0 + 6, get=getter(401, None))
    out = capsys.readouterr()
    blobs = [out.out, out.err, json.dumps(LV.key_status(root)), open(SP.status_path(root)).read(),
             json.dumps(db.execute("SELECT * FROM api_spend").fetchall())]
    assert all(KEY not in b for b in blobs)


def test_real_fetcher_only_talks_to_the_allowlisted_host():
    assert SP.USAGE_URL.startswith("https://api.darkbloom.dev/") and LV.http_get_json("https://evil.example/v1/payments/usage", KEY) == (0, None)


def test_removing_the_key_clears_the_spend_status(tmp_path):
    db, root = make(tmp_path)
    SP.ingest(db, root, T0 + 5, get=getter(401, None))
    LV.key_post(root, b'{"key": null}', T0)
    assert LV.key_status(root)["api_spend"] is None


# --- contribution entries, tally account block, reconcile -----------------------------------------------------------

def add_totals(db, at, avail, wd):
    db.execute("INSERT INTO account_totals (at, count, total_micro_usd, available_micro_usd, withdrawable_micro_usd) VALUES (?,?,?,?,?)",
               (at, 1, 0, avail, wd))
    db.commit()


def test_contribution_is_a_valid_kind_and_not_income_or_expense(tmp_path):
    db, _ = make(tmp_path)
    assert AE.validate_entry({"kind": "contribution", "date": "2026-11-05", "amount_cents": 2500, "category": "other"}) is None
    AE.add_entry(db, {"kind": "contribution", "date": "2026-11-05", "amount_cents": 2500, "category": "other", "note": "card"}, 1)
    t = TL.build_month(db, "2026-11", T0)
    assert t["totals"]["other_income_cents"] == 0 and t["totals"]["entries_deductible_cents"] == 0
    assert all(r["entries"] == [] for r in t["machines"])
    a = t["account"]
    assert a["contribution_cents"] == 2500 and a["api_spend_draw_cents"] == 0
    assert a["items"] == [{"effect": "contribution", "kind": "contribution", "id": 1, "date": "2026-11-05", "amount_cents": 2500, "note": "card"}]
    s = AS.build(db, "2026-11-30", "month")
    assert s["receipts_micro"] == 0 and s["entries_business_micro"] == 0


def test_tally_account_block_schema_and_old_fields(tmp_path):
    db, root = make(tmp_path)
    SP.ingest(db, root, T0 + 50, get=getter(200, [row("b", T0 + 20, 123456, p=7, c=3), row("a", T0 + 10, 100000, p=1, c=2)]))
    t = TL.build_month(db, "2026-11", T0 + 10**7)
    assert t["schema_version"] == 2 == TL.SCHEMA_VERSION
    for k in ("month", "timezone", "day_boundary", "rounding", "generated_at", "final", "hash", "totals", "machines", "balances"):
        assert k in t
    acct = t["account"]
    assert acct["api_spend_draw_cents"] == 22   # 223456 micro -> 22 cents, rounded down once
    assert acct["items"] == [{"effect": "draw", "kind": "api_spend", "amount_cents": 22, "requests": 2, "prompt_tokens": 8, "completion_tokens": 5}]
    assert not any("api_spend" in c for c in t["totals"])   # the old totals columns are untouched
    assert TL.build_month(db, "2026-10", T0)["account"]["api_spend_draw_cents"] == 0
    assert "2026-11" in [m["month"] for m in TL.build_months(db, T0 + 10**7)["months"]]
    h = t["hash"]
    SP.ingest(db, root, T0 + 60, get=getter(200, [row("c", T0 + 30, 5000)] + [row("b", T0 + 20, 123456)]))
    assert TL.build_month(db, "2026-11", T0 + 10**7)["hash"] != h   # the account block is covered by the hash


def reconcile_db(tmp_path, earn, draw, avail0, wd0, avail1, wd1, contrib=0):
    db, root = make(tmp_path)
    lo, hi = T0 - 1000, T0 + 1000
    import bloom_power_lib as P
    add_totals(db, P.utc_iso(lo), avail0, wd0)
    add_totals(db, P.utc_iso(hi - 1), avail1, wd1)
    db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, completion_tokens, source_machine) VALUES ('e1', ?, ?, 'job', 1, 'm')", (T0, earn))
    SP.ingest(db, root, T0 + 5, get=getter(200, [row("d1", T0 + 1, draw)]))
    return SP.reconcile(db, lo, hi, contrib), db


def test_reconcile_names_which_explanation_the_data_supports(tmp_path):
    # earnings pay: withdrawable = +earn - draw, credits unchanged
    r, _ = reconcile_db(tmp_path, 5_000_000, 2_000_000, 10_000_000, 4_000_000, 13_000_000, 7_000_000)
    assert r["supported"] == "earnings_pay" and r["withdrawable_change_cents"] == 300 and r["draws_cents"] == 200
    # card credit pays: withdrawable = +earn, credits fall by draw
    r, _ = reconcile_db(tmp_path, 5_000_000, 2_000_000, 10_000_000, 4_000_000, 13_000_000, 9_000_000)
    assert r["supported"] == "credit_pays" and r["credits_change_cents"] == -200
    # card top-up during the month, earnings pay
    r, _ = reconcile_db(tmp_path, 5_000_000, 2_000_000, 10_000_000, 4_000_000, 18_000_000, 7_000_000, contrib=5_000_000)
    assert r["supported"] == "earnings_pay"
    # neither
    r, _ = reconcile_db(tmp_path, 5_000_000, 2_000_000, 10_000_000, 4_000_000, 10_000_000, 4_000_000)
    assert r["supported"] == "not_enough_data" and "neither" in r["why"]


def test_reconcile_needs_two_snapshots_and_some_spend(tmp_path):
    db, root = make(tmp_path)
    assert SP.reconcile(db, T0 - 5, T0 + 5)["supported"] == "not_enough_data"
    add_totals(db, "2026-11-10T11:59:00Z", 1, 1)
    assert SP.reconcile(db, T0 - 5, T0 + 5)["supported"] == "not_enough_data"


def test_summary_carries_the_reconcile_line(tmp_path):
    db, _ = make(tmp_path)
    s = AS.build(db, "2026-11-30", "month")
    assert s["darkbloom_reconcile"]["supported"] == "not_enough_data"
    assert AS.build(db, "2026-11-30", "month", machine="m4")["darkbloom_reconcile"] is None
