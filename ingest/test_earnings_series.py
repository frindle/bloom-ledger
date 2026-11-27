"""Earnings series for the graph: daily buckets in UTC, zero-fill, running totals and the month roll-up. Fake numbers."""
import datetime as dt
import json

import bloom_earnings_series as ES
from server_fixture import web  # noqa: F401

TZ = "America/Los_Angeles"


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


ROWS = [(utc(2026, 10, 30, 20), 3_000_000, "job"), (utc(2026, 10, 30, 21), 1_000_000, "sandbox"),
        (utc(2026, 11, 2, 15), 2_000_000, "base"), (utc(2026, 11, 2, 16), 500_000, "job")]


def test_days_are_zero_filled_with_running_total():
    s = ES.shape(ROWS, TZ)
    assert [d["date"] for d in s["days"]] == ["2026-10-30", "2026-10-31", "2026-11-01", "2026-11-02"]
    assert [d["earned_micro"] for d in s["days"]] == [4_000_000, 0, 0, 2_500_000]
    assert [d["cumulative_micro"] for d in s["days"]] == [4_000_000] * 3 + [6_500_000]
    assert s["days"][0]["inference_micro"] == 3_000_000 and s["days"][0]["sandbox_micro"] == 1_000_000 and s["days"][3]["base_micro"] == 2_000_000
    assert s["total_micro"] == 6_500_000


def test_month_rollup_adds_up_to_days():
    s = ES.shape(ROWS, TZ)
    assert [(m["month"], m["earned_micro"], m["days"], m["cumulative_micro"]) for m in s["months"]] == \
        [("2026-10", 4_000_000, 2, 4_000_000), ("2026-11", 2_500_000, 2, 6_500_000)]
    assert sum(m["earned_micro"] for m in s["months"]) == s["total_micro"] == sum(d["earned_micro"] for d in s["days"])
    assert s["months"][1]["base_micro"] == 2_000_000


def test_local_midnight_decides_the_day():
    # 2026-11-01 07:30 UTC is 23:30 on Oct 31 in Los Angeles (PDT ended 11-01 at 02:00 local; still PDT then)
    s = ES.shape([(utc(2026, 11, 1, 6, 30), 7, "job")], TZ)
    assert s["days"][0]["date"] == "2026-10-31"


def test_utc_midnight_decides_the_day():
    # The ledger buckets in UTC (Darkbloom's day): 23:59:59Z and 00:00:00Z fall on different days,
    # and a time just before local (Los Angeles) midnight stays on its UTC day.
    rows = [(utc(2026, 11, 1, 23, 59, 59), 1, "job"), (utc(2026, 11, 2, 0, 0, 0), 2, "job"), (utc(2026, 11, 2, 6, 30), 4, "job")]
    s = ES.shape(rows, "UTC")
    assert [(d["date"], d["earned_micro"]) for d in s["days"]] == [("2026-11-01", 1), ("2026-11-02", 6)]
    assert s["timezone"] == "UTC"
    assert [d["date"] for d in ES.shape([rows[2]], TZ)["days"]] == ["2026-11-01"]   # the same instant is Nov 1 locally


def test_build_uses_utc_whatever_the_electricity_zone(monkeypatch):
    import sqlite3
    import bloom_accounting_config as CF
    import bloom_accounting_index as AX
    monkeypatch.setenv("BLOOM_TIMEZONE", TZ)
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    db.execute("INSERT INTO earnings VALUES ('a', ?, 9, 'job', 'm', 'j', 1, 'm')", (utc(2026, 11, 2, 3, 0),))
    CF.set_setting(db, "local_timezone", TZ, "1970-01-01", 1)
    s = ES.build(db, today="2026-11-02")
    assert s["timezone"] == "UTC" and [d["date"] for d in s["days"]] == ["2026-11-02"]


def test_today_extends_the_chart_and_empty_is_empty():
    s = ES.shape(ROWS, TZ, today="2026-11-04")
    assert s["days"][-1]["date"] == "2026-11-04" and s["days"][-1]["cumulative_micro"] == 6_500_000
    assert ES.shape([], TZ) == {"timezone": TZ, "days": [], "months": [], "total_micro": 0}


def test_route_serves_series_and_rejects_queries(web):  # noqa: F811
    code, ctype, body = web("GET", "/v1/earnings/series")
    assert code == 200 and ctype == "application/json" and json.loads(body)["days"] == []
    assert web("GET", "/v1/earnings/series?x=1")[0] == 400
    assert web("POST", "/v1/earnings/series", body=b"{}")[0] in (404, 405, 501)
    code, ctype, body = web("GET", "/v1/invoice/months")
    assert code == 200 and json.loads(body)["months"] == []


def test_home_page_has_the_graph():
    import bloom_accounting_page as PG
    html = PG.render_page()
    assert 'id="graph"' in html and "/v1/earnings/series" in html and 'id="graph-month"' in html and html.count("<script>") == 1
