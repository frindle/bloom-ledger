"""Frozen test: bloom_accounting_admin.accounting_post for entries (synthetic)."""
import json

import bloom_accounting_admin as A
import bloom_accounting_entries as E
import bloom_ingest as I

NOW = 1_790_000_000.5


def post(tmp_path, payload, raw=None, path="/v1/accounting/entries"):
    db = I.open_db(tmp_path / "i.sqlite")
    body = raw if raw is not None else json.dumps(payload).encode()
    try:
        return A.accounting_post(path, {}, body, db, NOW), db
    except TypeError as e:
        raise AssertionError("signature must be accounting_post(path, headers, body, db, now): " + str(e))


ENTRY = {"kind": "cost", "date": "2026-10-20", "amount_cents": 1234, "category": "software"}


def test_add_entry_created(tmp_path):
    (code, obj), db = post(tmp_path, ENTRY)
    assert code == 201 and isinstance(obj["id"], int)
    rows = E.current_entries(db)
    assert [r["id"] for r in rows] == [obj["id"]] and rows[0]["amount_cents"] == 1234
    assert db.execute("SELECT created_at FROM acct_entries").fetchone()[0] == 1_790_000_000


def test_bad_bodies_and_paths(tmp_path):
    assert post(tmp_path, None, raw=b"{nope")[0] == (400, {"error": "bad request"})
    assert post(tmp_path, None, raw=b"[1]")[0] == (400, {"error": "bad request"})
    assert post(tmp_path, dict(ENTRY, amount_cents=0))[0] == (400, {"error": "bad amount"})
    assert post(tmp_path, ENTRY, path="/v1/accounting/nope")[0] == (404, {"error": "not found"})
