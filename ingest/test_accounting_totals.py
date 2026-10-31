"""Frozen test: bloom_accounting_index.parse_totals_line / store_totals (synthetic numbers)."""
import json

import bloom_accounting_index as A
import bloom_ingest as I

SNAP = {"at": "2026-10-20T00:00:00Z", "count": 10, "total_micro_usd": 5000, "available_balance_micro_usd": 400,
        "withdrawable_balance_micro_usd": 300, "history_limit": 1000}


def test_parse_totals_line():
    assert A.parse_totals_line(json.dumps(SNAP)) == {"at": "2026-10-20T00:00:00Z", "count": 10, "total_micro_usd": 5000,
                                                     "available_micro_usd": 400, "withdrawable_micro_usd": 300}
    r = A.parse_totals_line(json.dumps({"at": "x", "count": -1, "total_micro_usd": 1.5, "available_balance_micro_usd": True}))
    assert r == {"at": "x", "count": None, "total_micro_usd": None, "available_micro_usd": None, "withdrawable_micro_usd": None}


def test_unusable_lines_give_none():
    for bad in ("junk", "[1]", "null", json.dumps({"count": 1}), json.dumps({"at": ""}), json.dumps({"at": 5})):
        assert A.parse_totals_line(bad) is None, bad


def test_store_totals_last_snapshot_wins(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    later = dict(SNAP, total_micro_usd=9000)
    payload = "\n".join([json.dumps(SNAP), "junk", "", json.dumps(later), json.dumps(dict(SNAP, at="2026-10-21T00:00:00Z"))])
    assert A.store_totals(db, payload) == 3
    assert db.execute("SELECT COUNT(*) FROM account_totals").fetchone()[0] == 2
    assert db.execute("SELECT total_micro_usd FROM account_totals WHERE at=?", (SNAP["at"],)).fetchone()[0] == 9000
