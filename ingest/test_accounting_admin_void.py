"""Frozen test: bloom_accounting_admin.accounting_post void + settings paths."""
import json

import bloom_accounting_admin as A
import bloom_accounting_config as C
import bloom_accounting_entries as E
import bloom_ingest as I

ADMIN = "fixture-admin-token-0123456789abcdef"
NOW = 1_790_000_000


def setup(tmp_path):
    ap = tmp_path / "bloom_admin"
    ap.write_text(ADMIN + "\n")
    return ap, I.open_db(tmp_path / "i.sqlite")


def post(ap, db, path, payload):
    return A.accounting_post(path, {"Authorization": "Bearer " + ADMIN}, json.dumps(payload).encode(), ap, db, NOW)


def test_void_entry_path(tmp_path):
    ap, db = setup(tmp_path)
    i = E.add_entry(db, {"kind": "cost", "date": "2026-10-20", "amount_cents": 5, "category": "other"}, 1)
    assert post(ap, db, "/v1/accounting/entries/void", {"id": i}) == (200, {"ok": True})
    assert E.current_entries(db) == []
    assert post(ap, db, "/v1/accounting/entries/void", {"id": i}) == (404, {"error": "not found"})
    assert post(ap, db, "/v1/accounting/entries/void", {"id": "1"}) == (400, {"error": "bad id"})


def test_settings_path_sets_effective_value(tmp_path):
    ap, db = setup(tmp_path)
    r = post(ap, db, "/v1/accounting/settings", {"key": "kwh_rate_cents", "value": 12, "effective_from": "2026-10-01"})
    assert r == (200, {"ok": True})
    assert C.effective_settings(db, "2026-10-02")["values"]["kwh_rate_cents"] == 12


def test_settings_path_validation(tmp_path):
    ap, db = setup(tmp_path)
    assert post(ap, db, "/v1/accounting/settings", {"key": "bogus", "value": 1, "effective_from": "2026-10-01"}) == (400, {"error": "bad key"})
    assert post(ap, db, "/v1/accounting/settings", {"key": "kwh_rate_cents", "value": 1, "effective_from": "x"}) == (400, {"error": "bad effective_from"})
