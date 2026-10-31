"""Frozen test: settings.html loads GET /v1/settings and renders the machines table, health list and admin note."""
import copy

import dom_support as D

SETTINGS = {
    "generated_at": 1793300000, "admin_enabled": False,
    "machines": [{"id": "m4max", "last_seen": 1793299880, "objects": 573, "days_sealed": 12, "status": "reporting"},
                 {"id": "mini", "last_seen": None, "objects": 0, "days_sealed": 0, "status": "not-reporting-yet"}],
    "health": {"version": "bloom-ledger/1", "time": 1793300000, "data_bytes": 1572864,
               "objects": 12},
}


def load(tmp_path, settings=None, steps=None):
    data = copy.deepcopy(SETTINGS)
    data.update(settings or {})
    return D.run_page(tmp_path, {"/v1/settings": {"status": 200, "body": data}}, steps)


def test_machine_rows(tmp_path):
    res = load(tmp_path, steps=[{"do": "call", "fn": "reloadSettings"}])
    assert [f["url"] for f in res["fetches"]] == ["/v1/settings", "/v1/settings"], "window.reloadSettings() refetches"
    assert res["errors"] == [], res["errors"]
    assert D.rows(res) == [["m4max", "2 minutes ago", "573", "12", "reporting", ""],
                           ["mini", "never", "0", "0", "Not reporting yet", ""]], D.rows(res)
    assert res["fetches"][0]["url"] == "/v1/settings" and res["fetches"][0]["method"] == "GET"
    assert "authorization" not in res["fetches"][0]["headers"], "reading needs no admin token"


def test_empty_machine_list_has_a_message(tmp_path):
    res = load(tmp_path, {"machines": []})
    assert D.rows(res) == [["No machines yet."]], D.rows(res)


def test_health_list(tmp_path):
    res = load(tmp_path)
    health = D.find(res["dom"], "health")
    names = D.texts(health, "dt")
    values = D.texts(health, "dd")
    assert names == ["Version", "Server time", "Data size", "Objects"], names
    assert values == ["bloom-ledger/1", "2026-10-29 18:53 UTC", "1.5 MB", "12"], values


def test_read_only_note_and_disabled_form(tmp_path):
    res = load(tmp_path)
    note, form = D.find(res["dom"], "admin-note"), D.find(res["dom"], "add-form")
    controls = [n for n in D.walk(form) if n["tag"] in ("input", "button")]
    assert note["hidden"] is False and "Read-only" in note["text"] and "bloom_admin" in note["text"], note
    assert controls and all(c["disabled"] for c in controls), "the add form is disabled without an admin secret"
    res = load(tmp_path, {"admin_enabled": True})
    note, form = D.find(res["dom"], "admin-note"), D.find(res["dom"], "add-form")
    controls = [n for n in D.walk(form) if n["tag"] in ("input", "button")]
    assert note["hidden"] is True or note["text"].strip() == "", note
    assert controls and not any(c["disabled"] for c in controls)


def test_failed_load_is_explained_and_the_script_is_clean(tmp_path):
    res = D.run_page(tmp_path, {"/v1/settings": {"status": 200, "network_error": True}})
    note = D.find(res["dom"], "admin-note")
    assert "Can't reach the ledger" in note["text"] and note["hidden"] is False, note
    ok = load(tmp_path)
    assert ok["errors"] == [] and res["errors"] == [], (ok["errors"], res["errors"])
    assert ok["inner_html_writes"] == 0 and ok["local_storage_calls"] == 0 and ok["console"] == []
