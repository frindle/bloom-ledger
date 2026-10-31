"""Frozen test: bloom_alerts.evaluate_alerts and bloom_alerts.record_upgrades."""
import bloom_alerts as AL
import bloom_ingest as I

NOW = 1793300000.0


def db_with(tmp_path, rows, ots=()):
    db = I.open_db(tmp_path / "i.sqlite")
    for i, (mid, kind, at) in enumerate(rows):
        I.index_object(db, mid, kind, f"{i:064x}", 1, at)
    for mid, name, stamped, upgraded in ots:
        db.execute("INSERT INTO ots (machine_id, manifest, stamped_at, upgraded_at) VALUES (?, ?, ?, ?)",
                   (mid, name, stamped, upgraded))
    db.commit()
    return db


def test_all_quiet(tmp_path):
    db = db_with(tmp_path, [("m4max", "log", NOW - 60), ("m4max", "archive-run", NOW - 900)],
                 [("m4max", "manifest-2026-10-28.json", NOW - 3600, None)])
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


def test_ots_not_upgraded_and_thresholds(tmp_path):
    db = db_with(tmp_path, [("m4max", "archive-run", NOW)],
                 [("m4max", "manifest-2026-10-26.json", NOW - 172801, None),
                  ("m4max", "manifest-2026-10-25.json", NOW - 900000, NOW - 800000),
                  ("m4max", "manifest-2026-10-27.json", NOW - 172800, None)])
    assert AL.evaluate_alerts(db, NOW) == [
        {"alert": "ots-not-upgraded", "machine_id": "m4max", "manifest": "manifest-2026-10-26.json", "age_s": 172801}]
    custom = AL.evaluate_alerts(db, NOW, silent_s=10, ring_s=10, ots_s=10)
    assert [a["alert"] for a in custom] == ["ots-not-upgraded", "ots-not-upgraded"]


def test_record_upgrades(tmp_path):
    db = db_with(tmp_path, [], [("m4max", "manifest-2026-10-26.json", NOW - 10, None),
                                ("m4max", "manifest-2026-10-27.json", NOW - 10, None),
                                ("m4max", "manifest-2026-10-25.json", NOW - 10, NOW - 5),
                                ("m5ultra", "manifest-2026-10-26.json", NOW - 10, None)])
    n = AL.record_upgrades(db, "m4max", {"manifest-2026-10-26.json": "upgraded", "manifest-2026-10-27.json": "pending",
                                         "manifest-2026-10-25.json": "upgraded", "manifest-2099-01-01.json": "upgraded",
                                         "manifest-2026-10-28.json": "stamped"}, NOW)
    assert n == 1, "only a not-yet-upgraded row of THIS machine counts"
    rows = dict(((m, n), u) for m, n, u in db.execute("SELECT machine_id, manifest, upgraded_at FROM ots"))
    assert rows[("m4max", "manifest-2026-10-26.json")] == NOW
    assert rows[("m4max", "manifest-2026-10-27.json")] is None
    assert rows[("m4max", "manifest-2026-10-25.json")] == NOW - 5, "an earlier upgrade time is kept"
    assert rows[("m5ultra", "manifest-2026-10-26.json")] is None
    assert AL.record_upgrades(db, "m4max", {}, NOW) == 0 and AL.record_upgrades(db, "m4max", None, NOW) == 0
