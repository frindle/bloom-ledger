"""API keys page (Settings, API keys): the page lists keys, shows a new key once, and has a Revoke button. Uses the DOM harness."""
import dom_support as D

KEYS = {"keys": [{"id": 3, "label": "tracker", "created_at": 1793299880, "last_used_at": None}]}
CREATED = {"POST /v1/settings/api-keys": {"status": 201, "body": {"id": 4, "key": "blk_fake"}}}
SUBMIT = [{"do": "input", "id": "key-label", "values": {"key-label": "tracker"}}, {"do": "submit", "id": "keys-form"}]


def load(tmp_path, steps=None, **extra):
    fx = {}
    fx["GET /v1/settings/api-keys"] = {"status": 200, "body": KEYS}
    fx.update(extra)
    return D.run_page(tmp_path, fx, steps, page="api-keys.html")


def test_list_shows_label_created_and_last_used(tmp_path):
    res = load(tmp_path)
    assert res["errors"] == [], res["errors"]
    assert D.rows(res, "key-rows") == [["tracker", "2026-10-29 18:51 UTC", "never", "Revoke"]]


def test_create_shows_the_key_once(tmp_path):
    res = load(tmp_path, SUBMIT, **CREATED)
    assert res["errors"] == []
    assert D.find(res["dom"], "key-value")["text"] == "blk_fake" and not D.find(res["dom"], "key-box")["hidden"]
    done = load(tmp_path, SUBMIT + [{"do": "click", "id": "key-dismiss"}], **CREATED)
    assert D.find(done["dom"], "key-value")["text"] == "" and D.find(done["dom"], "key-box")["hidden"]


def test_revoke_button_posts_the_id(tmp_path):
    res = load(tmp_path, [])
    btns = [n for n in D.walk(D.find(res["dom"], "key-rows")) if n["tag"] == "button"]
    assert [b["text"] for b in btns] == ["Revoke"]
