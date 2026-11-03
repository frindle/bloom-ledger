import hashlib
import json

import bloom_ingest as I
import bloom_settings as BS


def _legacy(tmp_path, mid, token):
    p = tmp_path / "bloom_tokens"
    p.write_text("%s %s\n" % (mid, hashlib.sha256(token.encode()).hexdigest()))
    return p


def test_new_token_adopts_a_legacy_machine(tmp_path):
    tok_path, mpath = _legacy(tmp_path, "m4max", "old-token-123"), tmp_path / "machines.json"
    legacy = set(I.load_tokens(tok_path).values())
    code, obj = BS.admin_post("/v1/settings/machines/rotate", {}, json.dumps({"id": "m4max"}), mpath, 5, legacy)
    assert code == 200 and obj["id"] == "m4max"
    tokens = I.load_tokens(tok_path, mpath)
    assert tokens == {hashlib.sha256(obj["token"].encode()).hexdigest(): "m4max"}  # old hash no longer accepted
    assert json.loads(mpath.read_text())["machines"]["m4max"]["adopted"] is True


def test_rotate_still_refuses_unknown_and_revoked(tmp_path):
    tok_path, mpath = _legacy(tmp_path, "m4max", "old-token-123"), tmp_path / "machines.json"
    code, _ = BS.admin_post("/v1/settings/machines/rotate", {}, json.dumps({"id": "ghost"}), mpath, 5, {"m4max"})
    assert code == 404
    BS.revoke_machine(mpath, "m4max")
    code, _ = BS.admin_post("/v1/settings/machines/rotate", {}, json.dumps({"id": "m4max"}), mpath, 5, {"m4max"})
    assert code == 404


def test_legacy_line_wins_until_adopted(tmp_path):
    tok_path, mpath = _legacy(tmp_path, "m4max", "old-token-123"), tmp_path / "machines.json"
    mpath.write_text(json.dumps({"machines": {"m4max": {"hash": "a" * 64}}, "revoked": []}))
    assert set(I.load_tokens(tok_path, mpath)) == {hashlib.sha256(b"old-token-123").hexdigest()}
