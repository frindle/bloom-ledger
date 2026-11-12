"""The tally routes over a real server, and the server stays read-only for them."""
import json

from server_fixture import web  # noqa: F401


def test_tally_routes(web):
    code, ctype, body = web("GET", "/v1/tally/monthly?month=2026-10")
    assert code == 200 and ctype == "application/json" and json.loads(body)["final"] is False
    assert web("GET", "/v1/tally/monthly?month=nope")[0] == 400
    code, _, body = web("GET", "/v1/tally/months")
    assert code == 200 and json.loads(body)["months"] == []
    assert web("POST", "/v1/tally/monthly?month=2026-10", body=b"{}")[0] in (404, 405, 501)
