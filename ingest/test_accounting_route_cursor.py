"""Frozen test: bloom_accounting_index route and cursor."""
import bloom_accounting_index as A
import bloom_ingest as I


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
