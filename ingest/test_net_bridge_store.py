"""Frozen test (step 2): the November net-bytes sidecar fills the matching power minutes, in either order."""
import sqlite3

import bloom_accounting_index as A

NET = ["gpu_bytes_in", "gpu_bytes_out", "sandbox_bytes_in", "sandbox_bytes_out", "total_bytes_in", "total_bytes_out"]
SIDE = ("ts_utc,gpu_bytes_in,gpu_bytes_out,sandbox_bytes_in,sandbox_bytes_out,total_bytes_in,total_bytes_out\n"
        "2026-11-03T08:03:02Z,9944,43121,131362,6498012,5394618,8260981\n"
        "2026-11-03T08:04:02Z,,,0,0,6185501,\n")
T1, T2 = 1793692982, 1793693042


def fn(name):
    f = getattr(A, name, None)
    assert callable(f), "bloom_accounting_index." + name + " is missing"
    return f


def mk():
    db = sqlite3.connect(":memory:")
    A.create_schema(db)
    return db


def minute(db, ts):
    db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, dbk_state, other_work, tokens_delta)"
               " VALUES ('m', ?, 1, 60, 1, 'idle', 0, 0)", (ts,))


def net_of(db, ts, machine="m"):
    row = db.execute("SELECT " + ", ".join(NET) + " FROM power_minutes WHERE machine_id = ? AND ts = ?", (machine, ts)).fetchone()
    assert row is not None, "no such power minute"
    return list(row)


def test_sidecar_first_then_power_rows():
    db = mk()
    fn("store_net")(db, "m", SIDE)
    minute(db, T1)
    minute(db, T2)
    fn("apply_net_bridge")(db)
    assert net_of(db, T1) == [9944, 43121, 131362, 6498012, 5394618, 8260981]
    assert net_of(db, T2) == [None, None, 0, 0, 6185501, None]


def test_power_rows_first_headerless_increment_and_other_machine():
    db = mk()
    minute(db, T1)
    minute(db, T2)
    db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, dbk_state, other_work, tokens_delta)"
               " VALUES ('other', ?, 1, 60, 1, 'idle', 0, 0)", (T1,))
    fn("store_net")(db, "m", "2026-11-03T08:03:02Z,1,2,3,4,5,6\nnot-a-time,1,1,1,1,1,1\n\n")
    assert net_of(db, T1) == [1, 2, 3, 4, 5, 6], "a headerless increment uses the sidecar's own column order"
    assert net_of(db, T2) == [None] * 6
    assert net_of(db, T1, "other") == [None] * 6, "bytes only go to the same machine"
    assert db.execute("SELECT COUNT(*) FROM net_bridge").fetchone()[0] == 1
