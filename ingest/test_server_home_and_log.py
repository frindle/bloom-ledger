"""Frozen test: / is the accounting ledger page, /log is the machine log."""
import server as SV
from server_fixture import web  # noqa: F401


def test_root_is_the_ledger_and_log_is_the_machine_log(web):
    assert callable(SV.Handler.do_GET)
    status, ctype, body = web("GET", "/")
    assert status == 200 and ctype.startswith("text/html") and b"<title>Ledger</title>" in body and b'id="day-rows"' not in body
    status, ctype, body = web("GET", "/log")
    assert status == 200 and ctype.startswith("text/html") and b'id="day-rows"' in body
    assert web("GET", "/index.html")[2] == web("GET", "/")[2]

    status, _, body = web("GET", "/settings")
    assert status == 200 and b"<html" in body
    assert web("GET", "/nope")[0] == 404


def test_log_page_links_exist_in_the_log_view(web):
    body = web("GET", "/log")[2]
    assert b'href="/settings"' in body
    assert web("GET", "/")[2] != body
