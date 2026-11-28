"""Scoped API keys: creation, scope, refusal everywhere else, ref idempotency and void. Fake data, real server."""
import json
import sqlite3

import pytest

import bloom_accounting_entries as AE
import bloom_api_keys as AK
import bloom_auth as AU
import bloom_ingest as I
from server_fixture import post_object, web  # noqa: F401

H = {"Content-Type": "application/json", "Host": "127.0.0.1:1", "Origin": "http://127.0.0.1:1"}
ENTRY = {"kind": "cost", "date": "2026-10-20", "amount_cents": 500, "category": "supplies"}


def call(web, method, path, obj=None, cookie=None, key=None, origin=True):
    h = dict(H)
    if not origin:
        h.pop("Origin")
    if cookie:
        h["Cookie"] = cookie
    if key:
        h["Authorization"] = "Bearer " + key
    s, _c, body = web(method, path, body=None if obj is None else json.dumps(obj).encode(), headers=h)
    return s, json.loads(body or b"{}")


def login(web):
    AU._fails.clear()
    s, _o = call(web, "POST", "/v1/auth/setup", {"username": "me", "password": "longenough1", "timezone": "UTC", "rate": "0.15", "bloomgauge": False})
    assert s == 200
    return web.last_headers["set-cookie"].split(";")[0]


def make_key(web, cookie, label="tracker"):
    s, o = call(web, "POST", "/v1/settings/api-keys", {"label": label}, cookie)
    assert s == 201, o
    return o["key"], o["id"]


def test_create_needs_login_and_stores_only_a_hash(web):
    assert call(web, "POST", "/v1/settings/api-keys", {"label": "x"})[0] == 401
    ck = login(web)
    assert call(web, "POST", "/v1/settings/api-keys", {"label": "x"}, ck, origin=False)[0] == 403
    key, kid = make_key(web, ck)
    assert key.startswith("blk_") and len(key) >= 40
    row = web.db.execute("SELECT label, key_hash FROM bl_api_keys").fetchone()
    assert row[0] == "tracker" and row[1] == AK._hash(key) and key not in json.dumps(row)
    s, o = call(web, "GET", "/v1/settings/api-keys")
    assert o["keys"] == [{"id": kid, "label": "tracker", "created_at": o["keys"][0]["created_at"], "last_used_at": None}]
    assert key not in json.dumps(o) and "hash" not in json.dumps(o)


def test_label_is_required_and_bounded(web):
    ck = login(web)
    for bad in ("", "   ", "x" * 61, 5, None):
        assert call(web, "POST", "/v1/settings/api-keys", {"label": bad}, ck)[0] == 400


def test_key_adds_entry_without_cookie_or_origin_and_updates_last_used(web):
    ck = login(web)
    key, _ = make_key(web, ck)
    assert call(web, "POST", "/v1/accounting/entries", ENTRY, origin=False)[0] == 401
    s, o = call(web, "POST", "/v1/accounting/entries", ENTRY, key=key, origin=False)
    assert s == 201 and isinstance(o["id"], int)
    assert call(web, "GET", "/v1/settings/api-keys")[1]["keys"][0]["last_used_at"] is not None
    s, o2 = call(web, "POST", "/v1/accounting/entries/void", {"id": o["id"]}, key=key, origin=False)
    assert s == 200 and o2 == {"ok": True}


def test_key_attaches_receipt_and_reads_the_machine_list(web):
    ck = login(web)
    key, _ = make_key(web, ck)
    eid = call(web, "POST", "/v1/accounting/entries", ENTRY, key=key)[1]["id"]
    s, _c, _b = web("POST", "/v1/accounting/entries/%d/receipt" % eid, body=b"%PDF-1.4 fake",
                    headers={"Authorization": "Bearer " + key, "Content-Type": "application/pdf"})
    assert s not in (401, 403)
    s, o = call(web, "GET", "/v1/settings", key=key)
    assert s == 200 and "machines" in o


def test_key_is_refused_on_every_other_route(web):
    ck = login(web)
    key, kid = make_key(web, ck)
    for method, path in (("POST", "/v1/settings/machines"), ("POST", "/v1/settings/api-keys"), ("POST", "/v1/settings/api-keys/revoke"),
                         ("POST", "/v1/accounting/settings"), ("POST", "/v1/objects"), ("POST", "/v1/pair"),
                         ("GET", "/v1/settings/api-keys"), ("GET", "/v1/accounting/entries"), ("GET", "/v1/status")):
        assert call(web, method, path, {"label": "x", "id": kid}, key=key)[0] == 403, (method, path)
    assert len(AK.list_keys(web.db)) == 1


def test_unknown_or_revoked_key_is_401(web):
    ck = login(web)
    assert call(web, "POST", "/v1/accounting/entries", ENTRY, key="blk_" + "A" * 43)[0] == 401
    key, kid = make_key(web, ck)
    assert call(web, "POST", "/v1/accounting/entries", ENTRY, key=key)[0] == 201
    assert call(web, "POST", "/v1/settings/api-keys/revoke", {"id": kid}, ck)[0] == 200
    assert call(web, "POST", "/v1/accounting/entries", ENTRY, key=key)[0] == 401
    assert call(web, "GET", "/v1/settings", key=key)[0] == 401
    assert call(web, "POST", "/v1/settings/api-keys/revoke", {"id": kid}, ck)[0] == 404
    assert call(web, "GET", "/v1/settings/api-keys")[1]["keys"] == []


def test_machine_tokens_are_a_separate_path(web):
    ck = login(web)
    make_key(web, ck)
    assert call(web, "POST", "/v1/accounting/entries", ENTRY, key="mac1-token", origin=False)[0] == 401
    assert post_object(web, "mac1-token") == 201


def test_bearer_parsing_and_constant_time_compare():
    import inspect
    assert "compare_digest" in inspect.getsource(AK.verify)
    assert AK.bearer_key({"Authorization": "Bearer mac1-token"}) is None
    assert AK.bearer_key({"Authorization": "Basic blk_x"}) is None
    assert AK.bearer_key({"Authorization": "Bearer blk_abc"}) == "blk_abc"


def test_ref_makes_a_retry_idempotent(web):
    ck = login(web)
    key, _ = make_key(web, ck)
    e = dict(ENTRY, ref="order-1")
    s, o = call(web, "POST", "/v1/accounting/entries", e, key=key)
    assert s == 201
    s2, o2 = call(web, "POST", "/v1/accounting/entries", e, key=key)
    assert s2 == 200 and o2 == {"id": o["id"], "existing": True}
    assert web.db.execute("SELECT COUNT(*) FROM acct_entries").fetchone()[0] == 1
    assert call(web, "POST", "/v1/accounting/entries", dict(ENTRY, ref="order-2"), key=key)[0] == 201


def test_voided_ref_can_be_posted_again_and_the_old_row_stays(web):
    ck = login(web)
    key, _ = make_key(web, ck)
    e = dict(ENTRY, ref="order-1")
    first = call(web, "POST", "/v1/accounting/entries", e, key=key)[1]["id"]
    assert call(web, "POST", "/v1/accounting/entries/void", {"id": first}, key=key)[0] == 200
    s, o = call(web, "POST", "/v1/accounting/entries", e, key=key)
    assert s == 201 and o["id"] != first
    assert web.db.execute("SELECT COUNT(*) FROM acct_entries").fetchone()[0] == 2
    assert call(web, "POST", "/v1/accounting/entries", e, key=key)[1] == {"id": o["id"], "existing": True}
    assert call(web, "POST", "/v1/accounting/entries/void", {"id": o["id"]}, key=key)[0] == 200
    assert call(web, "POST", "/v1/accounting/entries", e, key=key)[0] == 201


def test_ref_validation_and_database_uniqueness(tmp_path):
    for bad in ("", "  ", "x" * 101, 5):
        assert AE.validate_entry(dict(ENTRY, ref=bad)) == "bad ref"
    assert AE.validate_entry(dict(ENTRY, ref="x" * 100)) is None and AE.validate_entry(ENTRY) is None
    db = I.open_db(tmp_path / "i.sqlite")
    AE.add_entry(db, dict(ENTRY, ref="a"), 1)
    AE.add_entry(db, ENTRY, 1)
    AE.add_entry(db, ENTRY, 1)
    with pytest.raises(sqlite3.IntegrityError):
        AE.add_entry(db, dict(ENTRY, ref="a"), 2)


def test_an_older_table_gets_the_ref_column(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    db.execute("CREATE TABLE acct_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, date TEXT NOT NULL,"
               " amount_cents INTEGER NOT NULL, category TEXT NOT NULL, machine_id TEXT, note TEXT, created_at INTEGER NOT NULL, voided_at INTEGER)")
    db.execute("INSERT INTO acct_entries (kind, date, amount_cents, category, created_at) VALUES ('cost', '2026-10-01', 5, 'other', 1)")
    AE.create_entries_table(db)
    assert AE.add_entry(db, dict(ENTRY, ref="r"), 2) == 2
    assert db.execute("SELECT ref FROM acct_entries ORDER BY id").fetchall() == [(None,), ("r",)]
