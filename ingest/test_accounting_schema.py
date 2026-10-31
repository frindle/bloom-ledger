"""Frozen test: bloom_accounting_index schema and reset."""
import bloom_accounting_index as A
import bloom_ingest as I


def names(db):
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_schema_is_idempotent(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    A.create_schema(db)
    assert set(A.TABLES) <= names(db) and "objects" in names(db)


def test_natural_keys_dedupe(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    for _ in range(2):
        db.execute("INSERT OR IGNORE INTO power_minutes (machine_id, ts, wh) VALUES ('m1', 100, 1.5)")
        db.execute("INSERT OR IGNORE INTO earnings (ledger_id, ts, micro_usd) VALUES ('L1', 100, 500)")
    assert db.execute("SELECT COUNT(*) FROM power_minutes").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM earnings").fetchone()[0] == 1


def test_reset_keeps_objects(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    I.index_object(db, "m1", "log", "b" * 64, 10, 1793300000.0)
    A.create_schema(db)
    db.execute("INSERT INTO acct_cursor (machine_id, sha256) VALUES ('m1', ?)", ("b" * 64,))
    db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd) VALUES ('L1', 100, 500)")
    A.reset(db)
    assert db.execute("SELECT COUNT(*) FROM earnings").fetchone()[0] == 0 and db.execute("SELECT COUNT(*) FROM acct_cursor").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM objects").fetchone()[0] == 1

