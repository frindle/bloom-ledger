"""Frozen test: per-machine acquisition field ("leased" | "purchased", default "leased"; informational only)."""
import json

import pytest

import bloom_ingest as I
import bloom_machine_profiles as MP


@pytest.fixture
def db(tmp_path):
    return I.open_db(tmp_path / "i.sqlite")


def test_validate_accepts_only_known_acquisitions_or_null():
    assert MP.validate_profile({"acquisition": "leased"}) == {}
    assert MP.validate_profile({"acquisition": "purchased"}) == {}
    assert MP.validate_profile({"acquisition": None}) == {}
    for bad in ("", "Leased", "rented", 1, True, ["leased"]):
        assert "acquisition" in MP.validate_profile({"acquisition": bad})


def test_default_is_leased_and_value_persists(db):
    assert MP.upsert_profile(db, "m1", {"model": "Test-Model 1"}, 1)["acquisition"] == "leased"
    assert MP.upsert_profile(db, "m1", {"acquisition": "purchased"}, 2)["acquisition"] == "purchased"
    assert MP.upsert_profile(db, "m1", {"model": "Test-Model 2"}, 3)["acquisition"] == "purchased"
    assert MP.list_profiles(db)["m1"]["acquisition"] == "purchased"
    assert MP.upsert_profile(db, "m1", {"acquisition": None}, 4)["acquisition"] == "leased"


def test_bad_acquisition_is_rejected_and_writes_nothing(db):
    assert MP.upsert_profile(db, "ok1", {"acquisition": "purchased"}, 1)["acquisition"] == "purchased"
    with pytest.raises(ValueError):
        MP.upsert_profile(db, "m1", {"acquisition": "rented"}, 1)
    assert list(MP.list_profiles(db)) == ["ok1"]


def test_old_database_without_the_column_is_migrated_in_place(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    db.execute("CREATE TABLE machine_profiles (machine_id TEXT PRIMARY KEY, display_name TEXT, model TEXT,"
               " lease_start TEXT, lease_monthly_cents INTEGER, active INTEGER NOT NULL DEFAULT 1, updated_at INTEGER NOT NULL)")
    db.execute("INSERT INTO machine_profiles VALUES ('old', 'Desk', NULL, NULL, 100, 1, 5)")
    db.commit()
    prof = MP.list_profiles(db)["old"]
    assert prof["acquisition"] == "leased" and prof["lease_monthly_cents"] == 100
    MP.create_table(db)
    assert [r[1] for r in db.execute("PRAGMA table_info(machine_profiles)")].count("acquisition") == 1


def test_profile_post_validates_and_returns_it(db, tmp_path):
    mp = tmp_path / "machines.json"
    mp.write_text("{}")
    code, obj = MP.profile_post("/v1/settings/machines/profile", json.dumps({"id": "m1", "acquisition": "purchased"}), db, mp, 1)
    assert code == 200 and obj["profile"]["acquisition"] == "purchased"
    code, obj = MP.profile_post("/v1/settings/machines/profile", json.dumps({"id": "m1", "acquisition": "rented"}), db, mp, 2)
    assert code == 400 and "acquisition" in obj["fields"]
    assert MP.list_profiles(db)["m1"]["acquisition"] == "purchased"
