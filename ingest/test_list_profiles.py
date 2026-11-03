"""Frozen test: bloom_machine_profiles.list_profiles."""
import bloom_ingest as I
import bloom_machine_profiles as MP


def test_empty_db_creates_the_table_and_returns_empty(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    assert MP.list_profiles(db) == {}
    assert db.execute("SELECT name FROM sqlite_master WHERE name = 'machine_profiles'").fetchone() is not None


def test_rows_map_to_profiles_with_a_bool_active(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    MP.create_table(db)
    db.execute("INSERT INTO machine_profiles (machine_id, display_name, model, lease_start, lease_monthly_cents, active, updated_at)"
               " VALUES ('m1', 'Desk', 'Test-Model 1', '2026-03-01', 100, 1, 10)")
    db.execute("INSERT INTO machine_profiles (machine_id, display_name, model, lease_start, lease_monthly_cents, active, updated_at)"
               " VALUES ('m2', NULL, NULL, NULL, NULL, 0, 11)")
    db.commit()
    assert MP.list_profiles(db) == {
        "m1": {"display_name": "Desk", "model": "Test-Model 1", "lease_start": "2026-03-01",
               "lease_monthly_cents": 100, "acquisition": "leased", "in_service": None, "purchase_cents": None, "active": True},
        "m2": {"display_name": None, "model": None, "lease_start": None, "lease_monthly_cents": None, "acquisition": "leased", "in_service": None, "purchase_cents": None, "active": False},
    }
    assert MP.list_profiles(db)["m1"]["active"] is True and MP.list_profiles(db)["m2"]["active"] is False
