"""Withdrawal requests found from balance snapshots. Synthetic numbers; nothing calls a network."""
import datetime as dt
import json
import sqlite3

import bloom_accounting_index as AX
import bloom_api_spend as SP
import bloom_withdrawals as WD


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def make():
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    SP.create_table(db)
    return db


def snap(db, day, hour, avail, withdr):
    at = dt.datetime(2030, 3, day, hour, tzinfo=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute("INSERT INTO account_totals (at, count, total_micro_usd, available_micro_usd, withdrawable_micro_usd) VALUES (?,?,?,?,?)",
               (at, 1, 0, avail, withdr))


def earn(db, n, day, hour, micro):
    db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind) VALUES (?,?,?,?)", ("e%d" % n, utc(2030, 3, day, hour), micro, "job"))


def spend(db, n, day, hour, micro):
    db.execute("INSERT INTO api_spend (request_id, ts, cost_micro_usd) VALUES (?,?,?)", ("r%d" % n, utc(2030, 3, day, hour), micro))


def test_a_drop_the_earnings_do_not_explain_is_a_request():
    db = make()
    snap(db, 1, 0, 100_000_000, 100_000_000)
    earn(db, 1, 1, 5, 4_000_000)
    snap(db, 2, 0, 104_000_000, 104_000_000)          # earnings only: no request
    earn(db, 2, 2, 5, 2_000_000)
    snap(db, 3, 0, 36_000_000, 36_000_000)            # 106 expected, 36 actual: 70 dollars left
    got = WD.detect(db)
    assert len(got) == 1 and got[0]["amount_cents"] == 7000
    assert got[0]["requested_at"] == "2030-03-03T00:00:00Z" and got[0]["since"] == "2030-03-02T00:00:00Z"
    assert got[0]["key"].startswith("w-") and WD.detect(db)[0]["key"] == got[0]["key"]


def test_api_draws_paid_from_withdrawable_are_not_a_request():
    db = make()
    snap(db, 1, 0, 50_000_000, 50_000_000)
    earn(db, 1, 1, 5, 3_000_000)
    spend(db, 1, 1, 6, 8_000_000)
    snap(db, 2, 0, 45_000_000, 45_000_000)            # +3 earned, -8 drawn = -5
    assert WD.detect(db) == []


def test_draws_paid_from_credits_do_not_hide_a_request():
    db = make()
    snap(db, 1, 0, 80_000_000, 50_000_000)            # credits 30
    earn(db, 1, 1, 5, 3_000_000)
    spend(db, 1, 1, 6, 8_000_000)
    snap(db, 2, 0, 50_000_000, 28_000_000)            # credits 22 (fell by the draws), withdrawable 28: 50 + 3 - 28 = 25 left
    assert [g["amount_cents"] for g in WD.detect(db)] == [2500]


def test_noise_inside_the_tolerance_and_missing_values_are_ignored():
    db = make()
    snap(db, 1, 0, 10_000_000, 10_000_000)
    snap(db, 2, 0, 9_970_000, 9_970_000)              # 3 cents of rounding
    db.execute("INSERT INTO account_totals (at, count, available_micro_usd, withdrawable_micro_usd) VALUES ('2030-03-03T00:00:00Z', 1, NULL, NULL)")
    snap(db, 4, 0, 10_000_000, 10_000_000)
    assert WD.detect(db) == []


def test_response_is_read_only_json_and_rejects_queries():
    db = make()
    snap(db, 1, 0, 10_000_000, 10_000_000)
    snap(db, 2, 0, 4_000_000, 4_000_000)
    code, ctype, data = WD.withdrawals_response(db, "/v1/withdrawals", utc(2030, 3, 5, 0))
    body = json.loads(data)
    assert (code, ctype) == (200, "application/json") and body["withdrawals"][0]["amount_cents"] == 600
    assert WD.withdrawals_response(db, "/v1/withdrawals?x=1", 0)[0] == 400
    assert WD.withdrawals_response(db, "/v1/other", 0)[0] == 404


def test_a_rise_matching_an_earlier_request_marks_it_refunded():
    db = make()
    snap(db, 1, 0, 100_000_000, 100_000_000)
    snap(db, 2, 0, 30_000_000, 30_000_000)            # 70 dollars requested
    snap(db, 3, 0, 100_000_000, 100_000_000)          # 70 comes back
    got = WD.detect(db)
    assert len(got) == 1 and got[0]["amount_cents"] == 7000
    assert got[0]["status"] == "refunded" and got[0]["refunded_at"] == "2030-03-03T00:00:00Z"
    assert got[0]["requested_at"] == "2030-03-02T00:00:00Z"


def test_a_rise_that_matches_no_request_is_ignored():
    db = make()
    snap(db, 1, 0, 100_000_000, 100_000_000)
    snap(db, 2, 0, 30_000_000, 30_000_000)            # 70 requested
    snap(db, 3, 0, 60_000_000, 60_000_000)            # 30 rise: not near 70
    snap(db, 4, 0, 90_000_000, 90_000_000)            # another 30 rise, still no match
    got = WD.detect(db)
    assert len(got) == 1 and got[0]["status"] == "requested" and got[0]["refunded_at"] is None
    db2 = make()
    snap(db2, 1, 0, 10_000_000, 10_000_000)
    snap(db2, 2, 0, 20_000_000, 20_000_000)           # rise with no earlier request at all
    assert WD.detect(db2) == []


def test_refund_matches_the_latest_close_request_not_an_older_one():
    db = make()
    snap(db, 1, 0, 200_000_000, 200_000_000)
    snap(db, 2, 0, 130_000_000, 130_000_000)          # 70.00 requested
    snap(db, 3, 0, 60_000_000, 60_000_000)            # 70.00 requested again
    snap(db, 4, 0, 130_000_000, 130_000_000)          # 70.00 rise: both fit equally, the latest wins
    got = WD.detect(db)
    assert [g["status"] for g in got] == ["requested", "refunded"]
    assert got[1]["refunded_at"] == "2030-03-04T00:00:00Z"
    snap(db, 5, 0, 130_700_000, 130_700_000)          # 0.70 rise: nothing close, ignored
    assert [g["status"] for g in WD.detect(db)] == ["requested", "refunded"]
    # a closer amount beats a later one
    db = make()
    snap(db, 1, 0, 200_000_000, 200_000_000)
    snap(db, 2, 0, 130_000_000, 130_000_000)          # 70.00
    snap(db, 3, 0, 60_600_000, 60_600_000)            # 69.40 (within 2% of a 70.00 rise)
    snap(db, 4, 0, 130_600_000, 130_600_000)          # 70.00 rise: exact beats later
    assert [g["status"] for g in WD.detect(db)] == ["refunded", "requested"]


def test_retry_after_refund_is_a_new_request():
    db = make()
    snap(db, 1, 0, 100_000_000, 100_000_000)
    snap(db, 2, 0, 30_000_000, 30_000_000)            # 70 requested
    snap(db, 3, 0, 100_000_000, 100_000_000)          # refunded
    earn(db, 1, 3, 5, 5_000_000)
    snap(db, 4, 0, 30_000_000, 30_000_000)            # 105 expected, 30 actual: 75 retried
    got = WD.detect(db)
    assert [(g["amount_cents"], g["status"]) for g in got] == [(7000, "refunded"), (7500, "requested")]
    assert got[0]["key"] != got[1]["key"] and got[1]["refunded_at"] is None
