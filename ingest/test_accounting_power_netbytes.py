"""Frozen test (step 1): the power CSV's per-minute network byte columns land in power_minutes; blank means not measured."""
import sqlite3

import bloom_accounting_index as A
import bloom_ingest as I

P = "power/power-log-2026-12.csv"
NET = ["gpu_bytes_in", "gpu_bytes_out", "sandbox_bytes_in", "sandbox_bytes_out", "total_bytes_in", "total_bytes_out"]
HDR = ",".join(A.LEGACY_POWER_COLUMNS + ["sandbox_jobs"] + NET)
BASE = "60,60,1,150,200,2.0,1,serving,0.5,1,10,m,0,50,0,,,0"


def mk(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    return db


def net_of(db, ts):
    row = db.execute("SELECT " + ", ".join(NET) + " FROM power_minutes WHERE ts = ?", (ts,)).fetchone()
    assert row is not None, "power minute was not stored"
    return list(row)


def test_byte_columns_stored_by_header_name(tmp_path):
    db = mk(tmp_path)
    rows = ["2026-12-01T00:00:00Z," + BASE + ",9944,43121,131362,6498012,5394618,8260981",
            "2026-12-01T00:01:00Z," + BASE + ",,,0,0,5000,"]
    assert A.store_power(db, "m1", "a" * 64, P, 0, HDR + "\n" + "\n".join(rows) + "\n") == (2, 0)
    assert net_of(db, 1796083200) == [9944, 43121, 131362, 6498012, 5394618, 8260981]
    assert net_of(db, 1796083260) == [None, None, 0, 0, 5000, None], "blank is not measured (NULL), 0 is measured"


def test_reordered_header_and_bad_values(tmp_path):
    db = mk(tmp_path)
    hdr = ",".join(["ts_utc", "total_bytes_out", "wh", "interval_s", "power_ok", "gpu_bytes_in", "total_bytes_in"])
    body = hdr + "\n2026-12-01T00:00:00Z,77,1.5,60,1,-5,abc\n"
    assert A.store_power(db, "m1", "b" * 64, P, 0, body) == (1, 0), "a bad byte value does not drop the minute"
    assert net_of(db, 1796083200) == [None, None, None, None, None, 77]


def test_legacy_rows_have_no_bytes_and_old_index_rebuilds(tmp_path):
    db = mk(tmp_path)
    legacy = ",".join(A.LEGACY_POWER_COLUMNS) + "\n2026-10-20T12:00:00Z,60,60,1,150,200,2.0,1,serving,0.5,1,10,m,0,50,0,,\n"
    assert A.store_power(db, "m1", "c" * 64, "power/power-log-2026-10.csv", 0, legacy) == (1, 0)
    assert net_of(db, 1792497600) == [None] * 6
    old = sqlite3.connect(":memory:")
    old.execute("CREATE TABLE acct_meta (k TEXT PRIMARY KEY, v TEXT)")
    old.execute("INSERT INTO acct_meta VALUES ('index_version', '3')")
    old.execute("CREATE TABLE power_minutes (machine_id TEXT NOT NULL, ts INTEGER NOT NULL, wh REAL, interval_s REAL, power_ok INTEGER,"
                " dbk_state TEXT, other_work INTEGER, tokens_delta INTEGER, sandbox_jobs INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (machine_id, ts))")
    A.create_schema(old)
    cols = [r[1] for r in old.execute("PRAGMA table_info(power_minutes)")]
    assert all(c in cols for c in NET), cols
