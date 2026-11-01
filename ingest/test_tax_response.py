"""Frozen test: bloom_accounting_tax.tax_response (routing for /tax and /v1/accounting/tax). Fake numbers."""
import csv
import datetime as dt
import io
import json
import sqlite3

import bloom_accounting_index as AX
import bloom_accounting_tax as T


def make():
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    ts = int(dt.datetime(2026, 10, 20, 20, 0, tzinfo=dt.timezone.utc).timestamp())
    db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, completion_tokens, source_machine) VALUES ('e', ?, 2000000, 'job', 9, 'm4')", (ts,))
    db.commit()
    return db


def test_json_report_and_view_selection():
    code, ctype, body = T.tax_response(make(), "/v1/accounting/tax?year=2026&view=hobby")
    rep = json.loads(body)
    assert (code, ctype) == (200, "application/json") and rep["view"] == "hobby" and rep["totals"] == {"income_micro": 2000000}
    code, _, body = T.tax_response(make(), "/v1/accounting/tax?year=2026")
    assert code == 200 and json.loads(body)["view"] == "business" and json.loads(body)["year"] == 2026


def test_csv_and_page_routes():
    code, ctype, body = T.tax_response(make(), "/v1/accounting/tax?year=2026&view=hobby&format=csv")
    rows = list(csv.reader(io.StringIO(body.decode())))
    assert (code, ctype) == (200, "text/csv; charset=utf-8") and rows[0] == ["month", "income_micro", "bp"]
    assert rows[10] == ["2026-10", "2000000", ""] and rows[-1] == ["Bookkeeping, not tax advice"]
    code, ctype, body = T.tax_response(make(), "/tax?year=2026")
    assert (code, ctype) == (200, "text/html; charset=utf-8") and b"Bookkeeping, not tax advice" in body and b"<title>Tax year 2026</title>" in body


def test_bad_input_and_unknown_path():
    for p in ("/v1/accounting/tax?year=abc", "/v1/accounting/tax?year=1999", "/v1/accounting/tax?year=2026&view=x",
              "/v1/accounting/tax?year=2026&format=xml", "/tax?year=3000"):
        assert T.tax_response(make(), p) == (400, "application/json", b'{"error": "bad request"}'), p
    assert T.tax_response(make(), "/other") == (404, "application/json", b'{"error": "not found"}')
