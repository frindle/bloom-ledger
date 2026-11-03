"""Frozen test: bloom_settings.machine_rows exposes the profile acquisition."""
import bloom_ingest as I
import bloom_machine_profiles as MP
import bloom_settings as S


def rows_for(tmp_path, fields_by_id):
    db = I.open_db(tmp_path / "i.sqlite")
    for mid, fields in fields_by_id.items():
        MP.upsert_profile(db, mid, fields, 1)
    return {r["id"]: r for r in S.machine_rows(db, tmp_path, 1793300000.0, [])}


def test_purchased_acquisition_is_in_the_row_profile(tmp_path):
    rows = rows_for(tmp_path, {"m4": {"acquisition": "purchased"}})
    assert rows["m4"]["profile"]["acquisition"] == "purchased"


def test_acquisition_defaults_to_leased_in_the_row_profile(tmp_path):
    rows = rows_for(tmp_path, {"m5": {"model": "Test-Model 1"}})
    assert rows["m5"]["profile"]["acquisition"] == "leased"
    assert sorted(rows["m5"]["profile"]) == ["acquisition", "display_name", "in_service", "lease_monthly_cents", "lease_start", "model", "purchase_cents"]
