"""Frozen test: bloom_settings.machine_rows and bloom_settings.ledger_health (the settings page data)."""
import bloom_ingest as I
import bloom_ledger as L
import bloom_settings as S

NOW = 1793300000.0


def seed(tmp_path, last_age=60):
    db = I.open_db(tmp_path / "i.sqlite")
    I.index_object(db, "m4max", "log", "a" * 64, 10, NOW - 3 * 86400)
    I.index_object(db, "m4max", "usage", "b" * 64, 5, NOW - 2 * 86400)
    I.index_object(db, "m4max", "log", "c" * 64, 7, NOW - last_age)
    day = I.utc_day(NOW - 3 * 86400)
    L.write_manifest(tmp_path / "ledger" / "m4max", L.make_manifest(day, "m4max", [], None))
    return db


def test_machine_row_and_health_fields(tmp_path):
    db = seed(tmp_path)
    assert S.machine_rows(db, tmp_path, NOW, []) == [
        {"id": "m4max", "last_seen": int(NOW - 60), "objects": 3, "days_sealed": 1, "status": "reporting"}]
    got = S.ledger_health(db, tmp_path, NOW, "bloom-ledger/9")
    assert got["version"] == "bloom-ledger/9" and got["time"] == int(NOW) and got["objects"] == 3, got
    assert sorted(got) == ["data_bytes", "objects", "time", "version"], "no OpenTimestamps/Bitcoin fields"


def test_silent_after_thirty_minutes(tmp_path):
    db = seed(tmp_path, last_age=1800)
    assert S.machine_rows(db, tmp_path, NOW, [])[0]["status"] == "reporting", "exactly 30 minutes is still reporting"
    db.execute("UPDATE objects SET received_at = received_at - 1 WHERE sha256 = ?", ("c" * 64,))
    db.commit()
    assert S.machine_rows(db, tmp_path, NOW, [])[0]["status"] == "silent"


def test_pre_registered_ids_are_listed_not_reporting_yet_and_rows_are_sorted(tmp_path):
    db = seed(tmp_path)
    rows = S.machine_rows(db, tmp_path, NOW, ["zeta", "m4max", "alpha"])
    assert [r["id"] for r in rows] == ["alpha", "m4max", "zeta"]
    assert rows[0] == {"id": "alpha", "last_seen": None, "objects": 0, "days_sealed": 0, "status": "not-reporting-yet"}
    assert rows[1]["objects"] == 3 and rows[1]["status"] == "reporting"
    assert rows[2]["status"] == "not-reporting-yet"


def test_pre_registered_machine_never_raises_silent_alert(tmp_path):
    import bloom_alerts as AL
    db = I.open_db(tmp_path / "i.sqlite")
    assert S.machine_rows(db, tmp_path, NOW, ["m5ultra"])[0]["status"] == "not-reporting-yet"
    assert [a for a in AL.evaluate_alerts(db, NOW) if a["machine_id"] == "m5ultra"] == []
    I.index_object(db, "m5ultra", "log", "d" * 64, 1, NOW - 5000)
    assert S.machine_rows(db, tmp_path, NOW, ["m5ultra"])[0]["status"] == "silent"
    assert AL.evaluate_alerts(db, NOW)[0]["alert"] == "machine-silent"


def test_health_data_bytes_sums_every_file_under_root(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    (tmp_path / "objects" / "m1" / "log").mkdir(parents=True)
    (tmp_path / "objects" / "m1" / "log" / "x.obj").write_bytes(b"x" * 1000)
    (tmp_path / "ledger").mkdir()
    (tmp_path / "ledger" / "y.json").write_bytes(b"y" * 234)
    want = sum(f.stat().st_size for f in tmp_path.rglob("*") if f.is_file())
    got = S.ledger_health(db, tmp_path, NOW, "v")
    assert got["data_bytes"] == want and want >= 1234, (got, want)
    assert got["objects"] == 0
