"""Test: bloom_alerts.evaluate_alerts (machine-silent and ring-snapshot-stale only)."""
import bloom_alerts as AL
import bloom_ingest as I

NOW = 1793300000.0


def db_with(tmp_path, rows):
    db = I.open_db(tmp_path / "i.sqlite")
    for i, (mid, kind, at) in enumerate(rows):
        I.index_object(db, mid, kind, f"{i:064x}", 1, at)
    db.commit()
    return db


def test_all_quiet(tmp_path):
    db = db_with(tmp_path, [("m4max", "log", NOW - 60), ("m4max", "archive-run", NOW - 900)])
    assert AL.evaluate_alerts(db, NOW) == []


def test_machine_silent_and_ring_stale(tmp_path):
    db = db_with(tmp_path, [("m4max", "log", NOW - 1801), ("m4max", "archive-run", NOW - 43201),
                            ("m5ultra", "log", NOW - 1800), ("m5ultra", "usage", NOW - 10)])
    got = AL.evaluate_alerts(db, NOW)
    assert got == [
        {"alert": "machine-silent", "machine_id": "m4max", "age_s": 1801},
        {"alert": "ring-snapshot-stale", "machine_id": "m4max", "age_s": 43201},
        {"alert": "ring-snapshot-stale", "machine_id": "m5ultra", "age_s": None},
    ], "exactly 1800 s is not silent; a machine with no archive-run ever is stale with age None"


def test_ring_uses_archive_run_only(tmp_path):
    db = db_with(tmp_path, [("m4max", "usage", NOW - 5), ("m4max", "lifecycle", NOW - 5),
                            ("m4max", "archive-run", NOW - 50000)])
    assert [a["alert"] for a in AL.evaluate_alerts(db, NOW)] == ["ring-snapshot-stale"]
