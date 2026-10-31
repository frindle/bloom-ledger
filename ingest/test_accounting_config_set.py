"""Frozen test: bloom_accounting_config create_settings_table / set_setting."""
import json

import pytest

import bloom_accounting_config as C
import bloom_ingest as I


def test_append_only_rows(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    C.create_settings_table(db)
    C.create_settings_table(db)
    C.set_setting(db, "county_fee_pct", 12.5, "2026-10-13", 1000)
    C.set_setting(db, "county_fee_pct", 14, "2027-01-01", 2000)
    rows = db.execute("SELECT key, effective_from, value_json, created_at FROM acct_settings ORDER BY created_at").fetchall()
    assert rows == [("county_fee_pct", "2026-10-13", "12.5", 1000), ("county_fee_pct", "2027-01-01", "14", 2000)]


def test_value_is_json_and_table_autocreated(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    C.set_setting(db, "dep_method", "section179", "2026-10-01", 5)
    assert json.loads(db.execute("SELECT value_json FROM acct_settings").fetchone()[0]) == "section179"
    C.set_setting(db, "m5_lease_start", None, "2026-10-01", 6)
    assert db.execute("SELECT COUNT(*) FROM acct_settings").fetchone()[0] == 2


def test_rejects_bad_key_and_date(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    for key, day in (("nope", "2026-10-01"), ("dep_method", "10/01/2026"), ("dep_method", "2026-1-1"), ("dep_method", None)):
        with pytest.raises(ValueError):
            C.set_setting(db, key, "x", day, 1)
    assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='acct_settings'").fetchone()[0] in (0, 1)
