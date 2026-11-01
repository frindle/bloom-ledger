"""Frozen test: GET /tax and GET /v1/accounting/tax on the real server. Fake numbers."""
import csv
import io
import json

import server as SV
from server_fixture import web  # noqa: F401


def test_json_report_route(web):
    assert callable(SV.Handler.do_GET)
    status, ctype, body = web("GET", "/v1/accounting/tax?year=2026&view=hobby")
    rep = json.loads(body)
    assert (status, ctype) == (200, "application/json") and rep["year"] == 2026 and rep["view"] == "hobby" and rep["totals"] == {"income_micro": 0}
    status, _, body = web("GET", "/v1/accounting/tax?year=2026")
    assert status == 200 and json.loads(body)["view"] == "business" and len(json.loads(body)["months"]) == 12


def test_csv_and_page_routes(web):
    status, ctype, body = web("GET", "/v1/accounting/tax?year=2026&format=csv")
    assert (status, ctype) == (200, "text/csv; charset=utf-8") and next(csv.reader(io.StringIO(body.decode())))[0] == "month"
    status, ctype, body = web("GET", "/tax?year=2026")
    assert (status, ctype) == (200, "text/html; charset=utf-8") and b"Bookkeeping, not tax advice" in body


def test_bad_requests(web):
    assert web("GET", "/v1/accounting/tax?year=abc")[0] == 400
    assert web("GET", "/tax?year=2026&view=zzz")[0] == 400
    assert web("GET", "/v1/accounting/taxes")[0] == 404
