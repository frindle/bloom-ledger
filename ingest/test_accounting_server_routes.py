"""Frozen test: server /v1/accounting routes (LAN guard, no admin key)."""
import json

import server as SV
from server_fixture import web  # noqa: F401

H = {"Host": "ledger.test", "Origin": "http://ledger.test"}
ENTRY = json.dumps({"kind": "cost", "date": "2026-10-20", "amount_cents": 1234, "category": "software"}).encode()


def test_add_list_and_void_without_a_key(web):
    assert callable(SV.Handler.do_POST)
    status, ctype, body = web("POST", "/v1/accounting/entries", ENTRY, headers=H)
    assert status == 201 and ctype == "application/json"
    eid = json.loads(body)["id"]
    listed = json.loads(web("GET", "/v1/accounting/entries")[2])["entries"]
    assert [e["id"] for e in listed] == [eid] and listed[0]["amount_cents"] == 1234
    assert web("POST", "/v1/accounting/entries/void", json.dumps({"id": eid}).encode(), headers=H)[0] == 200
    assert json.loads(web("GET", "/v1/accounting/entries")[2])["entries"] == []


def test_guard_rejections_write_nothing(web):
    assert web("POST", "/v1/accounting/entries", ENTRY)[0] == 403, "no Origin header"
    assert web("POST", "/v1/accounting/entries", ENTRY, headers=dict(H, Origin="http://evil.example"))[0] == 403
    status, _, body = web("POST", "/v1/accounting/entries", ENTRY, headers=dict(H, **{"X-Forwarded-For": "8.8.8.8"}))
    assert status == 403 and json.loads(body) == {"error": "local network only"}
    assert web("POST", "/v1/accounting/entries", ENTRY, headers=dict(H, **{"CF-Connecting-IP": "8.8.8.8"}))[0] == 403
    assert json.loads(web("GET", "/v1/accounting/entries")[2])["entries"] == []


def test_bad_bodies_and_paths(web):
    assert web("POST", "/v1/accounting/entries", b"x" * 5000, headers=H)[0] == 413
    assert web("POST", "/v1/accounting/entries", b"{nope", headers=H)[0] == 400
    assert web("POST", "/v1/accounting/nope", b"{}", headers=H)[0] == 404
