"""Frozen test: bloom_settings.admin_check LAN mode (no secret path)."""
import bloom_settings as S


def test_none_path_means_no_key_required():
    assert S.admin_check({}, None) is None
    assert S.admin_check({"Authorization": "Bearer whatever"}, None) is None


def test_real_path_still_enforced_when_none_is_allowed(tmp_path):
    assert S.admin_check({}, None) is None
    missing = tmp_path / "nope"
    assert S.admin_check({}, str(missing)) == (403, {"error": "admin disabled"})
    f = tmp_path / "k"
    f.write_text("secret-value")
    assert S.admin_check({}, str(f)) == (401, {"error": "unauthorized"})
    assert S.admin_check({"Authorization": "Bearer secret-value"}, str(f)) is None


def test_admin_post_works_in_lan_mode(tmp_path):
    import json
    mp = tmp_path / "machines.json"
    code, obj = S.admin_post("/v1/settings/machines", {}, json.dumps({"id": "m1"}).encode(), str(mp), 1.0)
    assert code == 201 and obj["token"]
