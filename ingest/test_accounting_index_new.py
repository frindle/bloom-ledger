"""Frozen test: bloom_accounting_index.index_new over real stored objects (synthetic data)."""
import hashlib
import json

import bloom_accounting_index as A
import bloom_ingest as I

NOW = 1793300000.0
HDR = ",".join(A.LEGACY_POWER_COLUMNS)


def put(db, root, machine, path, offset, payload):
    body = json.dumps({"path": path, "offset": offset, "bytes": len(payload)}, sort_keys=True).encode() + b"\n" + payload.encode()
    sha = hashlib.sha256(body).hexdigest()
    I.store_object(root, machine, "log", sha, body)
    I.index_object(db, machine, "log", sha, len(body), NOW)
    return sha


def seed(tmp_path):
    root = tmp_path / "data"
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    er = json.dumps({"_id": "L1", "created_at": "2026-10-20T12:00:00Z", "amount_micro_usd": 700, "job_id": "j"})
    pw = HDR + "\n2026-10-20T12:00:00Z,60,60,1,150,200,2.5,1,serving,0.5,1,10,m,0,50,0,,\n"
    tt = json.dumps({"at": "2026-10-20T13:00:00Z", "count": 1, "total_micro_usd": 700})
    put(db, root, "m1", "earnings-archive/earnings-2026-10.jsonl", 0, er + "\n")
    put(db, root, "m1", "power/power-log-2026-10.csv", 0, pw)
    put(db, root, "m1", "earnings-archive/totals.jsonl", 0, tt + "\n")
    put(db, root, "m1", "provider.log", 0, "ignored\n")
    return db, root


def counts(db):
    return [db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("earnings", "power_minutes", "account_totals")]


def test_routes_all_kinds_and_is_idempotent(tmp_path):
    db, root = seed(tmp_path)
    assert A.index_new(db, root) == 4 and counts(db) == [1, 1, 1]
    assert A.index_new(db, root) == 0 and counts(db) == [1, 1, 1]


def test_reset_then_reindex_equals_incremental(tmp_path):
    db, root = seed(tmp_path)
    A.index_new(db, root)
    before = db.execute("SELECT ledger_id, micro_usd, source_machine FROM earnings").fetchall()
    A.reset(db)
    assert counts(db) == [0, 0, 0]
    A.index_new(db, root)
    assert counts(db) == [1, 1, 1] and db.execute("SELECT ledger_id, micro_usd, source_machine FROM earnings").fetchall() == before


def test_bad_objects_are_skipped_not_fatal(tmp_path):
    db, root = seed(tmp_path)
    body = b"not json\nstuff"
    sha = hashlib.sha256(body).hexdigest()
    I.store_object(root, "m1", "log", sha, body)
    I.index_object(db, "m1", "log", sha, len(body), NOW)
    I.index_object(db, "m1", "log", "f" * 64, 5, NOW)  # row with no file on disk
    A.index_new(db, root)
    assert counts(db) == [1, 1, 1] and A.is_parsed(db, "m1", sha) and A.is_parsed(db, "m1", "f" * 64)
