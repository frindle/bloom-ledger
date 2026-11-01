"""Frozen test: / serves the rendered ledger page (markup plus script) and no longer reads accounting.html."""
import bloom_accounting_page as PG
import server as SV
from server_fixture import web  # noqa: F401


def test_root_serves_the_rendered_page(web):
    status, ctype, body = web("GET", "/")
    assert status == 200 and ctype.startswith("text/html")
    assert body == PG.render_page().encode()
    assert b"/v1/accounting/summary" in body and b'id="day-rows"' in body and b'href="/log"' in body
    assert web("GET", "/index.html")[2] == body


def test_log_is_unchanged_and_placeholder_constant_is_gone(web):
    assert not hasattr(SV, "ACCOUNTING")
    status, _, body = web("GET", "/log")
    assert status == 200 and b'id="machine-select"' in body and b'href="/settings"' in body
