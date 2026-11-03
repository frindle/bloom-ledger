"""Frozen test: bloom_settings.machine_rows merges machine profiles (synthetic values only)."""
import bloom_ingest as I
import bloom_machine_profiles as MP
import bloom_settings as S

NOW = 1793300000.0


def seed(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    I.index_object(db, "m4", "log", "a" * 64, 10, NOW - 60)
    I.index_object(db, "m5", "log", "b" * 64, 10, NOW - 5000)
    return db


def test_rows_without_a_profile_keep_the_old_shape(tmp_path):
    db = seed(tmp_path)
    rows = S.machine_rows(db, tmp_path, NOW, [])
    assert [sorted(r) for r in rows] == [["days_sealed", "id", "last_seen", "objects", "status"]] * 2


def test_a_profile_is_attached_without_the_active_flag(tmp_path):
    db = seed(tmp_path)
    MP.upsert_profile(db, "m4", {"display_name": "Desk", "model": "Test-Model 1", "lease_monthly_cents": 100}, 1)
    rows = {r["id"]: r for r in S.machine_rows(db, tmp_path, NOW, [])}
    assert rows["m4"]["profile"] == {"display_name": "Desk", "model": "Test-Model 1", "lease_start": None,
                                     "lease_monthly_cents": 100, "acquisition": "leased", "in_service": None, "purchase_cents": None}
    assert rows["m4"]["status"] == "reporting" and "profile" not in rows["m5"]


def test_removed_machine_with_history_stays_listed_as_removed(tmp_path):
    db = seed(tmp_path)
    MP.upsert_profile(db, "m5", {"display_name": "Old"}, 1)
    MP.deactivate_profile(db, "m5", 2)
    rows = {r["id"]: r for r in S.machine_rows(db, tmp_path, NOW, [])}
    assert rows["m5"]["status"] == "removed" and rows["m5"]["objects"] == 1
    assert rows["m5"]["profile"]["display_name"] == "Old" and rows["m4"]["status"] == "reporting"
    # a live token (re-added machine) wins over an inactive profile
    rows = {r["id"]: r for r in S.machine_rows(db, tmp_path, NOW, ["m5"])}
    assert rows["m5"]["status"] == "silent"


def test_profile_only_machines_are_listed_only_while_active(tmp_path):
    db = seed(tmp_path)
    MP.upsert_profile(db, "new1", {"model": "Test-Model 2"}, 1)
    MP.deactivate_profile(db, "gone1", 1)
    rows = {r["id"]: r for r in S.machine_rows(db, tmp_path, NOW, [])}
    assert sorted(rows) == ["m4", "m5", "new1"]
    assert rows["new1"]["status"] == "not-reporting-yet" and rows["new1"]["objects"] == 0
    assert rows["new1"]["profile"]["model"] == "Test-Model 2"
    ids = [r["id"] for r in S.machine_rows(db, tmp_path, NOW, ["zeta", "alpha"])]
    assert ids == sorted(ids)
