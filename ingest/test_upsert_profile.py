"""Frozen test: bloom_machine_profiles.upsert_profile (synthetic values only)."""
import pytest

import bloom_ingest as I
import bloom_machine_profiles as MP


@pytest.fixture
def db(tmp_path):
    return I.open_db(tmp_path / "i.sqlite")


def test_upsert_creates_then_merges_only_present_keys(db):
    p = MP.upsert_profile(db, "m1", {"display_name": " Desk ", "model": "Test-Model 1"}, 1000.9)
    assert p == {"display_name": "Desk", "model": "Test-Model 1", "lease_start": None, "lease_monthly_cents": None,
                 "acquisition": "leased", "in_service": None, "purchase_cents": None, "active": True}
    p = MP.upsert_profile(db, "m1", {"lease_start": "2026-03-01", "lease_monthly_cents": 100}, 2000)
    assert p == {"display_name": "Desk", "model": "Test-Model 1", "lease_start": "2026-03-01",
                 "lease_monthly_cents": 100, "acquisition": "leased", "in_service": None, "purchase_cents": None, "active": True}
    assert db.execute("SELECT updated_at FROM machine_profiles WHERE machine_id='m1'").fetchone()[0] == 2000
    p = MP.upsert_profile(db, "m1", {"lease_monthly_cents": None}, 3000)
    assert p["lease_monthly_cents"] is None and p["display_name"] == "Desk"
    assert db.execute("SELECT COUNT(*) FROM machine_profiles").fetchone()[0] == 1


def test_upsert_rejects_bad_id_or_fields_and_writes_nothing(db):
    for bad in ("", "has space", "-x", None, 5):
        with pytest.raises(ValueError):
            MP.upsert_profile(db, bad, {}, 1)
    with pytest.raises(ValueError):
        MP.upsert_profile(db, "m1", {"model": ""}, 1)
    with pytest.raises(ValueError):
        MP.upsert_profile(db, "m1", {"admin": "x"}, 1)
    assert MP.list_profiles(db) == {}


def test_upsert_reactivates_a_removed_machine(db):
    MP.upsert_profile(db, "m1", {"display_name": "Desk"}, 1)
    db.execute("UPDATE machine_profiles SET active = 0")
    db.commit()
    assert MP.upsert_profile(db, "m1", {"model": "Test-Model 2"}, 70)["active"] is True
