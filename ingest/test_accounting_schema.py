"""Frozen test: bloom_accounting_index schema, router, cursor, reset."""
import bloom_accounting_index as A
import bloom_ingest as I


def names(db):
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_schema_is_idempotent(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    A.create_schema(db)
    assert set(A.TABLES) <= names(db) and "objects" in names(db)


def test_route_by_meta_path():
    assert A.route("power/power-log-2026-10.csv") == "power"
    assert A.route("earnings-archive/earnings-2026-10-13.jsonl") == "earnings"
    assert A.route("earnings-archive/totals.jsonl") == "totals"
    for bad in ("provider.log", "power/power-log-2026-10.csv.bak", "../power/power-log-2026-10.csv", "", None, 5):
        assert A.route(bad) is None, bad


def test_cursor_is_per_machine(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    sha = "a" * 64
    assert not A.is_parsed(db, "m1", sha)
    A.mark_parsed(db, "m1", sha)
    A.mark_parsed(db, "m1", sha)
    assert A.is_parsed(db, "m1", sha) and not A.is_parsed(db, "m2", sha)


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
    A.mark_parsed(db, "m1", "b" * 64)
    db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd) VALUES ('L1', 100, 500)")
    A.reset(db)
    assert db.execute("SELECT COUNT(*) FROM earnings").fetchone()[0] == 0 and not A.is_parsed(db, "m1", "b" * 64)
    assert db.execute("SELECT COUNT(*) FROM objects").fetchone()[0] == 1
