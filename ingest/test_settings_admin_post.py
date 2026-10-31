"""Frozen test: bloom_settings.admin_post (POST /v1/settings/machines[/rotate|/revoke])."""
import hashlib
import json
import os

import bloom_ingest as I
import bloom_settings as S

ADMIN = "fixture-admin-token-0123456789abcdef"
NOW = 1793300000.0


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def env(tmp_path, admin=True):
    ap = tmp_path / "bloom_admin"
    if admin:
        ap.write_text(ADMIN + "\n")
    return str(ap), str(tmp_path / "machines.json")


def post(tmp_path, path, payload, token=ADMIN, admin=True, raw=None):
    ap, mp = env(tmp_path, admin)
    headers = {"Authorization": "Bearer " + token} if token is not None else {}
    body = raw if raw is not None else json.dumps(payload).encode()
    return S.admin_post(path, headers, body, ap, mp, NOW)


def tokens(tmp_path):
    return I.load_tokens(str(tmp_path / "absent"), str(tmp_path / "machines.json"))


def test_admin_disabled_and_unauthorized_never_touch_the_store(tmp_path):
    code, obj = post(tmp_path, "/v1/settings/machines", {"id": "m1"}, admin=False)
    assert (code, obj) == (403, {"error": "admin disabled"})
    for tok in (None, "wrong", ""):
        code, obj = post(tmp_path, "/v1/settings/machines", {"id": "m1"}, token=tok)
        assert (code, obj) == (401, {"error": "unauthorized"})
    assert not os.path.exists(tmp_path / "machines.json")


def test_add_returns_the_token_once(tmp_path):
    code, obj = post(tmp_path, "/v1/settings/machines", {"id": "m1"})
    assert code == 201 and sorted(obj) == ["id", "token"] and obj["id"] == "m1", (code, obj)
    assert tokens(tmp_path) == {sha(obj["token"]): "m1"}
    assert obj["token"] not in open(tmp_path / "machines.json").read()
    code, obj2 = post(tmp_path, "/v1/settings/machines", {"id": "m1"})
    assert code == 409 and "token" not in obj2, (code, obj2)


def test_bad_requests_are_400(tmp_path):
    for raw in (b"{not json", b"[]", b'{"id": 5}', b"{}", b'{"id": "bad id!"}', b""):
        code, obj = post(tmp_path, "/v1/settings/machines", None, raw=raw)
        assert code == 400 and list(obj) == ["error"], (raw, code, obj)
    assert not os.path.exists(tmp_path / "machines.json")


def test_rotate_issues_a_new_token_and_unknown_is_404(tmp_path):
    _, first = post(tmp_path, "/v1/settings/machines", {"id": "m1"})
    code, obj = post(tmp_path, "/v1/settings/machines/rotate", {"id": "m1"})
    assert code == 200 and obj["id"] == "m1" and obj["token"] != first["token"], (code, obj)
    assert tokens(tmp_path) == {sha(obj["token"]): "m1"}
    code, obj = post(tmp_path, "/v1/settings/machines/rotate", {"id": "ghost"})
    assert code == 404 and "token" not in obj


def test_revoke_and_unknown_route(tmp_path):
    _, first = post(tmp_path, "/v1/settings/machines", {"id": "m1"})
    code, obj = post(tmp_path, "/v1/settings/machines/revoke", {"id": "m1"})
    assert (code, obj) == (200, {"id": "m1", "revoked": True})
    assert tokens(tmp_path) == {}
    assert post(tmp_path, "/v1/settings/other", {"id": "m1"})[0] == 404
    assert post(tmp_path, "/v1/settings/machines/revoke", {"id": "bad id!"})[0] == 400
