"""Frozen test: server.py POST /v1/settings/machines[/rotate|/revoke|/profile|/remove] (LAN guard, no admin key, body cap)."""
import json

import server as SV
from server_fixture import post_object, web  # noqa: F401

H = {"Host": "ledger.test", "Origin": "http://ledger.test"}


def machines(web):
    return [m["id"] for m in json.loads(web("GET", "/v1/settings")[2])["machines"]]


def test_writes_work_on_the_lan_without_any_key(web):
    assert callable(SV.Handler.do_POST)
    status, ctype, body = web("POST", "/v1/settings/machines", b'{"id": "m1"}', headers=H)
    assert status == 201 and ctype == "application/json"
    assert post_object(web, json.loads(body)["token"]) == 201, "an added machine can ingest at once"
    assert machines(web) == ["m1", "studio"]


def test_guard_rejections_write_nothing(web):
    body = b'{"id": "m1"}'
    assert web("POST", "/v1/settings/machines", body)[0] == 403, "no Origin header"
    assert web("POST", "/v1/settings/machines", body, headers=dict(H, Origin="http://evil.example"))[0] == 403
    status, _, out = web("POST", "/v1/settings/machines", body, headers=dict(H, **{"X-Forwarded-For": "8.8.8.8"}))
    assert status == 403 and json.loads(out) == {"error": "local network only"}
    assert web("POST", "/v1/settings/machines", body, headers=dict(H, **{"CF-Connecting-IP": "8.8.8.8"}))[0] == 403
    for path in ("/v1/settings/machines/profile", "/v1/settings/machines/remove", "/v1/settings/machines/rotate"):
        assert web("POST", path, body)[0] == 403
    assert machines(web) == ["studio"], "nothing was added"


def test_rotate_and_revoke_cut_off_old_tokens(web):
    old = json.loads(web("POST", "/v1/settings/machines", b'{"id": "m1"}', headers=H)[2])["token"]
    new = json.loads(web("POST", "/v1/settings/machines/rotate", b'{"id": "m1"}', headers=H)[2])["token"]
    assert post_object(web, old) == 401 and post_object(web, new) == 201
    assert web("POST", "/v1/settings/machines/revoke", b'{"id": "m1"}', headers=H)[0] == 200
    assert post_object(web, new) == 401


def test_edit_and_remove_keep_history(web):
    token = json.loads(web("POST", "/v1/settings/machines", b'{"id": "m1"}', headers=H)[2])["token"]
    assert post_object(web, token) == 201
    status, _, out = web("POST", "/v1/settings/machines/profile",
                         b'{"id": "m1", "display_name": "Desk", "model": "Test-Model 1"}', headers=H)
    assert status == 200 and json.loads(out)["profile"]["display_name"] == "Desk"
    rows = {m["id"]: m for m in json.loads(web("GET", "/v1/settings")[2])["machines"]}
    assert rows["m1"]["profile"]["model"] == "Test-Model 1" and rows["m1"]["objects"] == 1
    assert web("POST", "/v1/settings/machines/profile", b'{"id": "m1", "model": ""}', headers=H)[0] == 400
    assert web("POST", "/v1/settings/machines/remove", b'{"id": "m1"}', headers=H) [0] == 200
    assert post_object(web, token) == 401, "the token is revoked"
    rows = {m["id"]: m for m in json.loads(web("GET", "/v1/settings")[2])["machines"]}
    assert rows["m1"]["status"] == "removed" and rows["m1"]["objects"] == 1, "its stored records stay"


def test_large_bodies_are_refused_and_nothing_secret_is_logged(web):
    assert web("POST", "/v1/settings/machines", b"x" * 5000, headers=H)[0] == 413
    assert web("POST", "/v1/settings/machines/profile", b"x" * 5000, headers=H)[0] == 413
    token = json.loads(web("POST", "/v1/settings/machines", b'{"id": "m1"}', headers=H)[2])["token"]
    logged = "\n".join(str(x) for x in web.lines)
    assert token not in logged and '{"id"' not in logged
