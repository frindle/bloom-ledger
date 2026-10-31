"""Frozen test: server.py POST /v1/settings/machines[/rotate|/revoke] (admin token, body cap, no secrets logged)."""
import json

import server as SV
from server_fixture import ADMIN, post_object, web  # noqa: F401


def test_writes_need_the_admin_token(web):
    assert callable(SV.Handler.do_POST)
    assert web("POST", "/v1/settings/machines", b'{"id": "m1"}')[0] == 403, "no admin secret on the server"
    web.admin_file.write_text(ADMIN)
    assert web("POST", "/v1/settings/machines", b'{"id": "m1"}')[0] == 401
    assert web("POST", "/v1/settings/machines", b'{"id": "m1"}', "wrong")[0] == 401
    assert json.loads(web("GET", "/v1/settings")[2])["machines"][0]["id"] == "studio", "nothing was added"


def test_added_machine_can_ingest_at_once(web):
    web.admin_file.write_text(ADMIN)
    status, ctype, body = web("POST", "/v1/settings/machines", b'{"id": "m1"}', ADMIN)
    assert status == 201 and ctype == "application/json"
    assert post_object(web, json.loads(body)["token"]) == 201
    ids = [m["id"] for m in json.loads(web("GET", "/v1/settings")[2])["machines"]]
    assert ids == ["m1", "studio"]


def test_rotate_and_revoke_cut_off_old_tokens(web):
    web.admin_file.write_text(ADMIN)
    old = json.loads(web("POST", "/v1/settings/machines", b'{"id": "m1"}', ADMIN)[2])["token"]
    new = json.loads(web("POST", "/v1/settings/machines/rotate", b'{"id": "m1"}', ADMIN)[2])["token"]
    assert post_object(web, old) == 401 and post_object(web, new) == 201
    assert web("POST", "/v1/settings/machines/revoke", b'{"id": "m1"}', ADMIN)[0] == 200
    assert post_object(web, new) == 401
    assert web("POST", "/v1/settings/machines/revoke", b'{"id": "studio"}', ADMIN)[0] == 200
    assert post_object(web, "studio-token") == 401, "a secret-file machine can be revoked too"


def test_large_bodies_are_refused(web):
    web.admin_file.write_text(ADMIN)
    assert web("POST", "/v1/settings/machines", b"x" * 5000, ADMIN)[0] == 413
    assert web("POST", "/v1/settings/machines", b'{"id": "' + b"a" * 4000 + b'"}', ADMIN)[0] == 400


def test_nothing_secret_is_logged(web):
    web.admin_file.write_text(ADMIN)
    token = json.loads(web("POST", "/v1/settings/machines", b'{"id": "m1"}', ADMIN)[2])["token"]
    web("POST", "/v1/settings/machines", b"x" * 5000, ADMIN)
    web("GET", "/v1/settings")
    logged = "\n".join(str(x) for x in web.lines)
    assert ADMIN not in logged and token not in logged and '{"id"' not in logged
