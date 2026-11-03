import sqlite3

import bloom_accounting_index as AX
import bloom_accounting_report as RP

LATE = AX.WRAPPER_FIX_TS + 60


def test_system_daemons_alone_are_not_other_work():
    r = {"other_work": "1", "other_procs": "cpu>150%:corespotlightd;cpu>150%:backupd"}
    assert AX.other_work_flag(LATE, r) == 0


def test_real_work_still_flags():
    assert AX.other_work_flag(LATE, {"other_work": "1", "other_procs": "cpu>150%:corespotlightd;ollama-worker.py"}) == 1
    assert AX.other_work_flag(LATE, {"other_work": "1", "other_procs": "local-endpoint-client:Python"}) == 1
    assert AX.other_work_flag(LATE, {"other_work": "1", "other_procs": ""}) == 1


def test_vm_only_cleared_when_sandbox_job_ran():
    r = {"other_work": "1", "other_procs": AX.VM_ENTRY + ";cpu>150%:corespotlightd"}
    assert AX.other_work_flag(LATE, r) == AX.VM_ONLY
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    for ts, jobs in ((LATE, 1), (LATE + 60, 0)):
        db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, dbk_state, other_work, tokens_delta,"
                   " sandbox_jobs) VALUES ('m', ?, 1.0, 60, 1, 'serving', ?, 0, ?)", (ts, AX.VM_ONLY, jobs))
    AX.apply_sandbox_bridge(db)
    got = dict(db.execute("SELECT ts, other_work FROM power_minutes").fetchall())
    assert got == {LATE: 0, LATE + 60: AX.VM_ONLY}


def test_sandbox_minutes_counted_without_rates():
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, dbk_state, other_work, tokens_delta,"
               " sandbox_jobs) VALUES ('m', ?, 1.0, 60, 1, 'serving', 0, 0, 1)", (LATE,))
    rows = RP.day_rows(db, "UTC", "2026-11-03", "2026-11-03")
    assert rows[0]["sandbox_minutes"] == 1 and rows[0]["paid_minutes"] == 1
