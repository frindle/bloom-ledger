"""Frozen test: server.scheduler runs the accounting index on each tick (synthetic data)."""
import server as S
from scheduler_fixture import tick  # noqa: F401


def test_tick_indexes_new_log_objects(tick):
    assert callable(S.scheduler)
    db, logs = tick()
    assert db.execute("SELECT ledger_id, micro_usd FROM earnings").fetchall() == [("L1", 700)]
    assert any("accounting indexed 1" in m for m in logs), logs


def test_failing_index_does_not_kill_the_tick(tick):
    db, logs = tick(fail=True)
    assert any("scheduler error RuntimeError" in m for m in logs), logs
