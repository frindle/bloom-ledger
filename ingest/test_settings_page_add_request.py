"""Frozen test: settings.html Add machine request, request, table refresh and server refusals."""
import json

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


def test_add_sends_the_request_and_refreshes(tmp_path):
    res = D.run_page(tmp_path, fetch_table(), [UNLOCK, ADD])
    assert len(posts(res)) == 1, "one POST to /v1/settings/machines"
    post = posts(res)[0]
    assert post["url"] == "/v1/settings/machines" and json.loads(post["body"]) == {"id": "m9"}
    assert post["headers"]["authorization"] == "Bearer " + ADMIN
    assert post["headers"]["content-type"] == "application/json"
    assert [f["url"] for f in res["fetches"] if f["method"] == "GET"] == ["/v1/settings", "/v1/settings"], "table refreshed"
    assert D.find(res["dom"], "new-id")["value"] == "" and "tok-123" not in json.dumps(res["session"])
    assert res["local_storage_calls"] == 0 and res["errors"] == [] and "tok-123" not in "".join(res["console"])


def test_server_refusals_refusals_are_explained(tmp_path):
    res = D.run_page(tmp_path, fetch_table(401, {"error": "unauthorized"}), [UNLOCK, ADD])
    assert "not accepted" in D.find(res["dom"], "admin-note")["text"] and KEY not in res["session"], res["session"]
    assert D.find(res["dom"], "onboarding")["hidden"] is True
    res = D.run_page(tmp_path, fetch_table(409, {"error": "exists"}), [UNLOCK, ADD])
    assert "already exists" in D.find(res["dom"], "form-error")["text"] and KEY in res["session"]
    assert D.find(res["dom"], "onboarding")["hidden"] is True and "tok-123" not in json.dumps(res["dom"])
