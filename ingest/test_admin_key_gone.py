"""Frozen test: bloom_settings.admin_check (the Bearer-secret check) is deleted."""
import inspect
import json

import bloom_settings as S


def test_admin_check_is_gone():
    assert not hasattr(S, "admin_check"), "bloom_settings.admin_check must be deleted"
    assert "admin_check" not in inspect.getsource(S)


def test_settings_writes_still_work_without_a_key(tmp_path):
    code, obj = S.admin_post("/v1/settings/machines", {}, json.dumps({"id": "m1"}).encode(), str(tmp_path / "m.json"), 1.0)
    assert code == 201 and obj["token"]
