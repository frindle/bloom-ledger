"""Frozen test: GET /v1/accounting/summary."""
import json

import server as SV
from server_fixture import web  # noqa: F401

H = {"Host": "ledger.test", "Origin": "http://ledger.test"}


def test_summary_defaults_and_entries(web):
    assert callable(SV.Handler.do_GET)
    web("POST", "/v1/accounting/entries", json.dumps({"kind": "cost", "date": "2026-10-20", "amount_cents": 1234, "category": "software"}).encode(), headers=H)
    status, ctype, body = web("GET", "/v1/accounting/summary?period=month&today=2026-10-31")
    s = json.loads(body)
    assert status == 200 and ctype == "application/json"
    assert (s["start"], s["end"], s["period"]) == ("2026-10-01", "2026-10-31", "month")
    assert [e["amount_cents"] for e in s["entries"]] == [1234]
    assert s["power"]["note"] == "grid rates, solar credit not applied"


def test_bad_period_and_machine_filter(web):
    assert web("GET", "/v1/accounting/summary?period=decade&today=2026-10-31")[0] == 400
    assert web("GET", "/v1/accounting/summary?today=nope")[0] == 400
    s = json.loads(web("GET", "/v1/accounting/summary?period=ytd&machine=m4&today=2026-10-31")[2])
    assert s["machine"] == "m4" and s["period"] == "ytd" and s["days"] == []
