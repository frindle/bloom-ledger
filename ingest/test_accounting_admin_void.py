"""Frozen test: bloom_accounting_admin.accounting_post void + settings paths."""
import json

import bloom_accounting_admin as A
import bloom_accounting_config as C
import bloom_accounting_entries as E
import bloom_ingest as I

NOW = 1_790_000_000


def setup(tmp_path):
    return None, I.open_db(tmp_path / "i.sqlite")


def post(ap, db, path, payload):
    try:
        return A.accounting_post(path, {}, json.dumps(payload).encode(), db, NOW)
    except TypeError as e:
        raise AssertionError("signature must be accounting_post(path, headers, body, db, now): " + str(e))


def test_void_entry_path(tmp_path):
    ap, db = setup(tmp_path)
    i = E.add_entry(db, {"kind": "cost", "date": "2026-10-20", "amount_cents": 5, "category": "other"}, 1)
    assert post(ap, db, "/v1/accounting/entries/void", {"id": i}) == (200, {"ok": True})
    assert E.current_entries(db) == []
    assert post(ap, db, "/v1/accounting/entries/void", {"id": i}) == (404, {"error": "not found"})
    assert post(ap, db, "/v1/accounting/entries/void", {"id": "1"}) == (400, {"error": "bad id"})


def test_settings_path_sets_effective_value(tmp_path):
    ap, db = setup(tmp_path)
    r = post(ap, db, "/v1/accounting/settings", {"key": "county_fee_pct", "value": 12, "effective_from": "2026-10-01"})
    assert r == (200, {"ok": True})
    assert C.effective_settings(db, "2026-10-02")["values"]["county_fee_pct"] == 12


def test_settings_path_validation(tmp_path):
    ap, db = setup(tmp_path)
    assert post(ap, db, "/v1/accounting/settings", {"key": "bogus", "value": 1, "effective_from": "2026-10-01"}) == (400, {"error": "bad key"})
    assert post(ap, db, "/v1/accounting/settings", {"key": "county_fee_pct", "value": 1, "effective_from": "x"}) == (400, {"error": "bad effective_from"})
