"""Frozen test: bloom_machine_profiles.deactivate_profile."""
import pytest

import bloom_ingest as I
import bloom_machine_profiles as MP


@pytest.fixture
def db(tmp_path):
    return I.open_db(tmp_path / "i.sqlite")


def test_deactivate_keeps_the_row_and_its_fields(db):
    MP.upsert_profile(db, "m1", {"display_name": "Desk"}, 1)
    assert MP.deactivate_profile(db, "m1", 50.7) is None
    assert MP.list_profiles(db)["m1"] == {"display_name": "Desk", "model": None, "lease_start": None,
                                           "lease_monthly_cents": None, "acquisition": "leased", "in_service": None, "purchase_cents": None, "active": False}
    assert db.execute("SELECT COUNT(*), updated_at FROM machine_profiles").fetchone() == (1, 50)


def test_deactivate_an_unknown_machine_inserts_an_inactive_row(db):
    assert MP.deactivate_profile(db, "ghost", 60) is None
    assert MP.list_profiles(db) == {"ghost": {"display_name": None, "model": None, "lease_start": None,
                                              "lease_monthly_cents": None, "acquisition": "leased", "in_service": None, "purchase_cents": None, "active": False}}


def test_deactivate_rejects_a_bad_id_and_never_deletes(db):
    MP.upsert_profile(db, "m1", {}, 1)
    for bad in ("bad id", "", None, 3):
        with pytest.raises(ValueError):
            MP.deactivate_profile(db, bad, 1)
    assert list(MP.list_profiles(db)) == ["m1"]
