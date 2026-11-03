import sqlite3
import bloom_accounting_index as AX


def test_bridge_sets_sandbox_jobs_in_either_order():
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    AX.store_sandbox(db, "m", "ts_utc,sandbox_jobs\n2026-11-03T06:30:04Z,2\n2026-11-03T06:31:04Z,0\n")
    hdr = ",".join(AX.LEGACY_POWER_COLUMNS)
    db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, dbk_state, other_work, tokens_delta) VALUES ('m', 1793687404, 1, 60, 1, 'idle', 0, 0)")
    AX.apply_sandbox_bridge(db)
    assert db.execute("SELECT sandbox_jobs FROM power_minutes").fetchone()[0] == 2


def test_route():
    assert AX.route("power/sandbox-jobs-2026-11.csv") == "sandbox"
