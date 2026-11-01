"""Frozen test: bloom_machine_profiles.create_table."""
import bloom_ingest as I
import bloom_machine_profiles as MP


def test_create_table_is_idempotent_and_has_the_columns(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    assert MP.create_table(db) is None
    MP.create_table(db)
    cols = [r[1] for r in db.execute("PRAGMA table_info(machine_profiles)")]
    assert cols == ["machine_id", "display_name", "model", "lease_start", "lease_monthly_cents", "active", "updated_at"]


def test_create_table_keeps_existing_rows(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    MP.create_table(db)
    db.execute("INSERT INTO machine_profiles (machine_id, updated_at) VALUES ('m1', 5)")
    db.commit()
    MP.create_table(db)
    row = db.execute("SELECT machine_id, active, updated_at FROM machine_profiles").fetchall()
    assert row == [("m1", 1, 5)], "active defaults to 1 and the row survives"
