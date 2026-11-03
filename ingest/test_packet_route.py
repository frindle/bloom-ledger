"""The year-end packet is served at /tax/packet and linked from the tax page. Fake data."""
import sqlite3

import bloom_accounting_index as AX
import bloom_accounting_tax as AT
import bloom_accounting_taxpage as TP


def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    AX.create_schema(c)
    return c


def test_packet_route_serves_html_for_the_year():
    code, ctype, body = AT.tax_response(db(), "/tax/packet?year=2026")
    assert code == 200 and ctype.startswith("text/html") and b"<title>Tax packet 2026</title>" in body


def test_packet_route_rejects_bad_year():
    assert AT.tax_response(db(), "/tax/packet?year=x")[0] == 400
    assert AT.tax_response(db(), "/tax/packet?year=1999")[0] == 400


def test_tax_page_links_the_packet():
    assert 'id="packet"' in TP.tax_page(2026) and '"/tax/packet?year="' in TP.tax_page(2026)


def test_server_routes_the_packet():
    assert '"/tax/packet"' in open(__import__("os").path.join(__import__("os").path.dirname(__file__), "server.py")).read()
