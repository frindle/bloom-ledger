"""Tests for the redesigned ingest/settings.html (machine table, add form, health, no admin token)."""
import copy
import json
import re
from pathlib import Path

import dom_support as D

HERE = Path(__file__).resolve().parent
TOKENS = ["paper", "card", "ink", "muted", "rule", "sealed", "waiting", "missing", "serif", "mono"]
COLUMNS = ["Machine id", "Display name", "Model", "Lease start", "Lease $/month", "Last seen", "Days sealed", "Status", "Actions"]
PROFILE = {"display_name": "Studio", "model": "M4 Max", "lease_start": "2026-01-15", "lease_monthly_cents": 12345}
NO_PROFILE = {"display_name": None, "model": None, "lease_start": None, "lease_monthly_cents": None}
SETTINGS = {
    "machines": [{"id": "m4max", "last_seen": 1793299880, "objects": 573, "days_sealed": 12, "status": "reporting", "profile": PROFILE},
                 {"id": "mini", "last_seen": None, "objects": 0, "days_sealed": 0, "status": "not-reporting-yet", "profile": NO_PROFILE}],
    "health": {"version": "bloom-ledger/1", "time": 1793300000, "data_bytes": 1572864, "objects": 12},
}


def one(profile=None):
    return {"machines": [{"id": "m4max", "last_seen": 1793299880, "objects": 5, "days_sealed": 2, "status": "reporting",
                          "profile": PROFILE if profile is None else profile}]}


def fixtures(settings=None, **posts):
    data = copy.deepcopy(SETTINGS)
    data.update(settings or {})
    fx = {"/v1/settings": {"status": 200, "body": data}}
    for path, (status, body) in posts.items():
        fx["POST /v1/settings/machines" + path] = {"status": status, "body": body}
    return fx


def load(tmp_path, settings=None, steps=None, **posts):
    return D.run_page(tmp_path, fixtures(settings, **posts), steps)


def post_calls(res):
    return [f for f in res["fetches"] if f["method"] == "POST"]


def get_calls(res):
    return [f for f in res["fetches"] if f["method"] == "GET"]


def table_row_inputs(res):
    body = D.find(res["dom"], "machine-rows")
    return [[n for n in D.walk(tr) if n["tag"] == "input"] for tr in body["children"] if tr["tag"] == "tr"]


def row_errors(res):
    body = D.find(res["dom"], "machine-rows")
    return [n for n in D.walk(body) if "error" in n["class"].split() and not n["hidden"]]


def css_tokens(text):
    return {n: v.strip() for n, v in re.findall(r"--(\w+):\s*([^;]+);", text)}


def test_table_has_nine_columns_and_a_caption():
    html = (HERE / "settings.html").read_text()
    assert re.search(r'<table[^>]*id="machines"', html) and 'id="machine-rows"' in html and "<caption" in html
    heads = re.findall(r'<th scope="col">([^<]*)</th>', html)
    assert heads == COLUMNS, heads


def test_rows_show_every_column(tmp_path):
    res = load(tmp_path)
    assert res["errors"] == [], res["errors"]
    assert D.rows(res) == [["m4max", "", "", "", "", "2 minutes ago", "12", "reporting", "SaveNew tokenRemove"],
                           ["mini", "", "", "", "", "never", "0", "Not reporting yet", "SaveNew tokenRemove"]], D.rows(res)
    first, second = table_row_inputs(res)
    assert [i["value"] for i in first] == ["Studio", "M4 Max", "2026-01-15", "123.45"], first
    assert [i["attrs"].get("type") for i in first] == ["text", "text", "date", "number"]
    assert [i["value"] for i in second] == ["", "", "", ""]
    assert get_calls(res)[0]["url"] == "/v1/settings" and "authorization" not in get_calls(res)[0]["headers"]


def test_row_buttons_have_the_agreed_labels_and_classes(tmp_path):
    res = load(tmp_path, one())
    body = D.find(res["dom"], "machine-rows")
    buttons = [(b["text"], b["class"]) for b in D.walk(body) if b["tag"] == "button"]
    assert buttons == [("Save", "primary"), ("New token", ""), ("Remove", "danger")], buttons


def test_empty_machine_list_has_a_message(tmp_path):
    res = load(tmp_path, {"machines": []})
    assert D.rows(res) == [["No machines yet. Add one below."]], D.rows(res)
    cell = D.find(res["dom"], "machine-rows")["children"][0]["children"][0]
    assert cell["attrs"].get("colspan") == "9"


def test_health_list(tmp_path):
    res = load(tmp_path)
    health = D.find(res["dom"], "health")
    assert D.texts(health, "dt") == ["Version", "Server time", "Data size", "Objects"]
    assert D.texts(health, "dd") == ["bloom-ledger/1", "2026-10-29 18:53 UTC", "1.5 MB", "12"]


def test_relative_time_ranges(tmp_path):
    now = SETTINGS["health"]["time"]
    machines = [{"id": name, "last_seen": now - secs, "objects": 1, "days_sealed": 0, "status": "silent", "profile": NO_PROFILE}
                for name, secs in (("a", 30), ("b", 1800), ("c", 3 * 3600), ("d", 3 * 86400))]
    res = load(tmp_path, {"machines": machines})
    assert [r[5] for r in D.rows(res)] == ["30 seconds ago", "30 minutes ago", "3 hours ago", "3 days ago"], D.rows(res)


def test_failed_load_shows_the_page_error(tmp_path):
    ok = load(tmp_path)
    assert D.find(ok["dom"], "page-error")["hidden"] is True
    for fetch in ({"/v1/settings": {"status": 200, "network_error": True}}, {"/v1/settings": {"status": 500, "body": {"error": "boom"}}}):
        res = D.run_page(tmp_path, fetch)
        err = D.find(res["dom"], "page-error")
        assert "Can't reach the ledger" in err["text"] and err["hidden"] is False, err
        assert D.rows(res) == [] and res["errors"] == [], (D.rows(res), res["errors"])


def test_save_posts_the_row_profile(tmp_path):
    res = load(tmp_path, one(), [{"do": "click", "sel": ".primary"}], **{"/profile": (200, {"ok": True})})
    assert res["errors"] == [], res["errors"]
    (post,) = post_calls(res)
    assert post["url"] == "/v1/settings/machines/profile" and post["headers"]["content-type"] == "application/json"
    assert "authorization" not in post["headers"]
    assert json.loads(post["body"]) == {"id": "m4max", "display_name": "Studio", "model": "M4 Max",
                                        "lease_start": "2026-01-15", "lease_monthly_cents": 12345}
    assert "Saved." in D.rows(res)[0][8]
    assert len(get_calls(res)) == 1, "saving does not reload the table"


def test_save_sends_nulls_for_an_empty_profile(tmp_path):
    res = load(tmp_path, one(NO_PROFILE), [{"do": "click", "sel": ".primary"}], **{"/profile": (200, {"ok": True})})
    (post,) = post_calls(res)
    assert json.loads(post["body"]) == dict(NO_PROFILE, id="m4max")


def test_save_refusals_are_explained_in_the_row(tmp_path):
    step = [{"do": "click", "sel": ".primary"}]
    res = load(tmp_path, one(), step, **{"/profile": (400, {"fields": {"model": "Model is too long.", "lease_start": "Lease start must be a date."}})})
    (err,) = row_errors(res)
    assert err["text"] == "Model is too long. Lease start must be a date.", err
    res = load(tmp_path, one(), step, **{"/profile": (404, {})})
    assert row_errors(res)[0]["text"] == "Unknown machine."
    res = load(tmp_path, one(), step, **{"/profile": (403, {})})
    assert "local network" in row_errors(res)[0]["text"]
    res = load(tmp_path, one(), step, **{"/profile": (500, {})})
    assert row_errors(res)[0]["text"] == "The server refused that change."


def test_remove_needs_two_clicks(tmp_path):
    click = {"do": "click", "sel": ".danger"}
    res = load(tmp_path, one(), [click], **{"/remove": (200, {"ok": True})})
    assert post_calls(res) == [] and "Confirm" in D.rows(res)[0][8], D.rows(res)
    res = load(tmp_path, one(), [click, click], **{"/remove": (200, {"ok": True})})
    (post,) = post_calls(res)
    assert post["url"] == "/v1/settings/machines/remove" and json.loads(post["body"]) == {"id": "m4max"}
    assert "authorization" not in post["headers"]
    assert len(get_calls(res)) == 2, "the table reloads after a removal"
    res = load(tmp_path, one(), [click, click], **{"/remove": (404, {})})
    assert row_errors(res)[0]["text"] == "Unknown machine." and len(get_calls(res)) == 1


def test_add_machine_shows_the_token_once(tmp_path):
    add = {"do": "submit", "id": "add-form", "values": {"new-id": "m9"}}
    res = load(tmp_path, steps=[add], **{"": (201, {"id": "m9", "token": "tok-123"})})
    assert res["errors"] == [], res["errors"]
    (post,) = post_calls(res)
    assert post["url"] == "/v1/settings/machines" and json.loads(post["body"]) == {"id": "m9"}
    assert post["headers"]["content-type"] == "application/json" and "authorization" not in post["headers"]
    assert len(get_calls(res)) == 2, "the table reloads after adding"
    box = D.find(res["dom"], "token-box")
    assert box["hidden"] is False and D.find(res["dom"], "token-value")["text"] == "tok-123"
    assert "m9" in D.find(res["dom"], "token-title")["text"]
    assert D.find(res["dom"], "new-id")["value"] == "" and D.find(res["dom"], "form-error")["hidden"] is True
    assert "tok-123" not in "".join(res["console"]) and "tok-123" not in json.dumps(res["session"])


def test_token_can_be_copied_and_dismissed(tmp_path):
    steps = [{"do": "submit", "id": "add-form", "values": {"new-id": "m9"}}, {"do": "click", "id": "token-copy"}]
    res = load(tmp_path, steps=steps, **{"": (201, {"id": "m9", "token": "tok-123"})})
    assert res["clipboard"] == ["tok-123"]
    res = load(tmp_path, steps=steps + [{"do": "click", "id": "token-dismiss"}], **{"": (201, {"id": "m9", "token": "tok-123"})})
    assert D.find(res["dom"], "token-box")["hidden"] is True and D.find(res["dom"], "token-value")["text"] == ""


def test_bad_machine_ids_are_rejected_locally(tmp_path):
    for bad in ("", "-lead", ".lead", "has space", "slash/id", "x" * 65):
        res = load(tmp_path, steps=[{"do": "submit", "id": "add-form", "values": {"new-id": bad}}])
        err = D.find(res["dom"], "form-error")
        assert post_calls(res) == [] and err["hidden"] is False and "Machine id must be" in err["text"], (bad, err)
    for good in ("a", "m4.max_1-b", "9" + "x" * 63):
        res = load(tmp_path, steps=[{"do": "submit", "id": "add-form", "values": {"new-id": good}}], **{"": (201, {"id": good, "token": "t"})})
        assert [json.loads(p["body"])["id"] for p in post_calls(res)] == [good], good


def test_add_refusals_are_explained(tmp_path):
    add = [{"do": "submit", "id": "add-form", "values": {"new-id": "m9"}}]
    for status, body, want in ((409, {}, "already exists"), (403, {}, "local network"),
                               (400, {"fields": {"id": "Id is invalid."}}, "Id is invalid."), (500, {}, "refused")):
        res = load(tmp_path, steps=add, **{"": (status, body)})
        err = D.find(res["dom"], "form-error")
        assert want in err["text"] and err["hidden"] is False, (status, err)
        assert D.find(res["dom"], "token-box")["hidden"] is True


def test_no_admin_token_machinery(tmp_path):
    html = (HERE / "settings.html").read_text()
    for gone in ("sessionStorage", "Authorization", "admin-token", "admin-form", "admin-note", "bloom_admin"):
        assert gone not in html, gone
    res = load(tmp_path, steps=[{"do": "submit", "id": "add-form", "values": {"new-id": "m9"}}], **{"": (201, {"id": "m9", "token": "t"})})
    assert res["session"] == {} and res["errors"] == [] and res["console"] == []
    assert res["inner_html_writes"] == 0 and res["local_storage_calls"] == 0


def test_links_and_headings():
    html = (HERE / "settings.html").read_text()
    assert html.lstrip().lower().startswith("<!doctype html>") and "<h1>Settings</h1>" in html
    assert '<a href="/">' in html and '<a href="/settings/accounting">' in html
    for heading in ("Machines", "Add a machine", "Ledger health"):
        assert f">{heading}</h2>" in html, heading
    assert re.search(r'<label for="new-id">', html) and 'id="new-id"' in html and ":focus-visible" in html


def test_reuses_the_dashboard_css_tokens():
    mine = css_tokens((HERE / "settings.html").read_text())
    theirs = css_tokens((HERE / "dashboard.html").read_text())
    for name in TOKENS:
        assert name in mine and mine[name] == theirs[name], f"--{name}: {mine.get(name)!r} vs {theirs[name]!r}"
