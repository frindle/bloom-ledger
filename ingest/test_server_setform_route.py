"""Frozen test: GET /settings/accounting on the real server."""
import server as SV
from server_fixture import web  # noqa: F401


def test_accounting_settings_page_is_served(web):
    assert callable(SV.Handler.do_GET)
    status, ctype, body = web("GET", "/settings/accounting")
    assert (status, ctype) == (200, "text/html; charset=utf-8")
    assert b"<title>Accounting settings</title>" in body and b'id="acct-form"' in body and b"Confirm with CPA" in body


def test_form_has_all_fields_and_neighbouring_routes_are_unchanged(web):
    assert web("GET", "/settings/accounting")[2].count(b"data-key=") == 11
    status, ctype, body = web("GET", "/settings")
    assert status == 200 and ctype == "text/html; charset=utf-8" and b"Accounting settings" not in body
    assert web("GET", "/settings/accounting/x")[0] == 404
    assert web("GET", "/settings/other")[0] == 404
