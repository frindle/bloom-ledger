"""Frozen test: bloom_accounting_index.store_power (synthetic rows)."""
import bloom_accounting_index as A
import bloom_ingest as I

HDR = ",".join(A.LEGACY_POWER_COLUMNS)
P = "power/power-log-2026-10.csv"


def row(ts, wh="2.0"):
    return f"{ts},60,60,1,150,200,{wh},1,serving,0.5,1,10,m,0,50,0,,"


def mk(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    return db


def test_header_from_offset_zero_then_headerless_increment(tmp_path):
    db = mk(tmp_path)
    assert A.store_power(db, "m1", "a" * 64, P, 0, HDR + "\n" + row("2026-10-20T12:00:00Z") + "\n") == (1, 0)
    assert A.store_power(db, "m1", "b" * 64, P, 500, row("2026-10-20T12:01:00Z", "3.0") + "\n") == (1, 0)
    assert db.execute("SELECT COUNT(*), SUM(wh) FROM power_minutes").fetchone() == (2, 5.0)


def test_overlapping_reship_does_not_double_count(tmp_path):
    db = mk(tmp_path)
    body = HDR + "\n" + row("2026-10-20T12:00:00Z") + "\n" + row("2026-10-20T12:01:00Z") + "\n"
    assert A.store_power(db, "m1", "a" * 64, P, 0, body)[0] == 2
    assert A.store_power(db, "m1", "c" * 64, P, 0, body + row("2026-10-20T12:02:00Z") + "\n") == (1, 0)
    assert db.execute("SELECT COUNT(*) FROM power_minutes").fetchone()[0] == 3


def test_bad_rows_early_rows_and_no_header_fallback(tmp_path):
    db = mk(tmp_path)
    out = A.store_power(db, "m2", "d" * 64, P, 900, "\n".join([row("2026-10-20T12:00:00Z"), "junk,1", row("2026-10-12T00:00:00Z")]))
    assert out == (1, 1)
    assert db.execute("SELECT n FROM acct_parse_errors WHERE machine_id='m2'").fetchone()[0] == 1
    assert A.store_power(db, "m2", "e" * 64, P, 1900, row("2026-10-12T00:00:00Z"), since_ts=0) == (1, 0)
