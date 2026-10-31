"""Frozen test: settings.html admin token (per tab) and the local checks of the Add machine form."""
import dom_support as D

SETTINGS = {"generated_at": 1793300000, "admin_enabled": True, "machines": [],
            "health": {"version": "v", "time": 1793300000, "data_bytes": 10, "objects": 0}}
ADMIN = "fixture-admin-token-0123456789abcdef"
KEY = "bloom-admin-token"
UNLOCK = {"do": "submit", "id": "admin-form", "values": {"admin-token": ADMIN}}
ADD = {"do": "submit", "id": "add-form", "values": {"new-id": "m9"}}


def fetch_table(post_status=201, post_body=None):
    return {"/v1/settings": {"status": 200, "body": SETTINGS},
            "POST /v1/settings/machines": {"status": post_status, "body": post_body or {"id": "m9", "token": "tok-123"}}}


def posts(res):
    return [f for f in res["fetches"] if f["method"] == "POST"]


def test_admin_token_is_kept_per_tab_only(tmp_path):
    res = D.run_page(tmp_path, fetch_table(), [UNLOCK])
    assert res["session"] == {KEY: ADMIN}, res["session"]
    assert D.find(res["dom"], "admin-token")["value"] == "", "the field is cleared after saving"
    assert D.find(res["dom"], "admin-token")["attrs"].get("type") == "password"
    assert "set for this tab" in D.find(res["dom"], "admin-state")["text"]
    assert res["local_storage_calls"] == 0 and res["errors"] == [] and ADMIN not in "".join(res["console"])


def test_add_is_refused_locally_without_token_or_with_a_bad_id(tmp_path):
    res = D.run_page(tmp_path, fetch_table(), [ADD])
    assert D.find(res["dom"], "form-error"), "form-error element missing"
    assert posts(res) == [] and "admin token" in D.find(res["dom"], "form-error")["text"]
    bad = {"do": "submit", "id": "add-form", "values": {"new-id": "bad id!"}}
    res = D.run_page(tmp_path, fetch_table(), [UNLOCK, bad])
    assert D.find(res["dom"], "form-error"), "form-error element missing"
    assert posts(res) == [] and "Machine id must be" in D.find(res["dom"], "form-error")["text"]
