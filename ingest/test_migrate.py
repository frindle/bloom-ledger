"""Upgrade step: an existing database keeps its old timezone/start/in-service values, a fresh one does not. Fake data."""
import sqlite3

import bloom_accounting_config as CF
import bloom_accounting_index as AX
import bloom_migrate as MIG


def mk():
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    return db


def test_fresh_database_gets_no_legacy_values(monkeypatch):
    monkeypatch.delenv("BLOOM_TIMEZONE", raising=False)
    monkeypatch.delenv("TZ", raising=False)
    db = mk()
    assert MIG.run(db, lambda m: None) == []
    v = CF.effective_settings(db, "2026-11-01")["values"]
    assert v["local_timezone"] == "UTC" and v["m4_in_service_date"] is None
    assert db.execute("SELECT v FROM acct_meta WHERE k='migration_legacy_defaults_v1'").fetchone()[0] == "fresh"


def test_existing_database_is_pinned_once(monkeypatch):
    monkeypatch.delenv("BLOOM_TIMEZONE", raising=False)
    monkeypatch.delenv("TZ", raising=False)
    db = mk()
    db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, model, job_id, completion_tokens, source_machine)"
               " VALUES ('L1', 1791900000, 5, 'inference', 'm', 'j', 0, 'm1')")
    assert MIG.run(db, lambda m: None) == ["migration_legacy_defaults_v1"]
    v = CF.effective_settings(db, "2026-11-01")["values"]
    assert (v["local_timezone"], v["ingest_from"], v["m4_in_service_date"]) == ("America/Los_Angeles", "2026-10-13", "2026-09-28")
    assert MIG.run(db, lambda m: None) == []          # second start does nothing
    n = db.execute("SELECT COUNT(*) FROM acct_settings").fetchone()[0]
    MIG.run(db, lambda m: None)
    assert db.execute("SELECT COUNT(*) FROM acct_settings").fetchone()[0] == n


def test_user_choice_is_not_overwritten():
    db = mk()
    CF.set_setting(db, "local_timezone", "Europe/Berlin", "2026-01-01", 1)
    db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, model, job_id, completion_tokens, source_machine)"
               " VALUES ('L1', 1791900000, 5, 'inference', 'm', 'j', 0, 'm1')")
    MIG.run(db, lambda m: None)
    assert CF.effective_settings(db, "2026-11-01")["values"]["local_timezone"] == "Europe/Berlin"


def test_ingest_cutoff_follows_setting(monkeypatch):
    for k in ("INGEST_FROM_TS", "BLOOM_INGEST_FROM"):
        monkeypatch.delenv(k, raising=False)
    db = mk()
    assert AX.resolve_since(db) == 0
    CF.set_setting(db, "ingest_from", "2026-10-13", "1970-01-01", 1)
    assert AX.resolve_since(db) == 1791849600     # 2026-10-13 00:00 UTC, exactly


def test_old_bind_mount_data_with_an_empty_volume_refuses_to_start(tmp_path):
    root, project = tmp_path / "data-volume", tmp_path / "project"
    root.mkdir()
    (project / "data" / "objects").mkdir(parents=True)
    msg = MIG.legacy_bind_data(root, project)
    assert msg and "BLOOM_DATA_DIR=./data" in msg and "BLOOM_KEYS_DIR=./data/secrets" in msg and "not touched" in msg
    # the volume already holds a ledger: nothing to say
    (root / "index.sqlite").write_text("")
    assert MIG.legacy_bind_data(root, project) is None


def test_fresh_install_and_unset_legacy_dir_start_normally(tmp_path):
    root = tmp_path / "data-volume"
    root.mkdir()
    assert MIG.legacy_bind_data(root, tmp_path / "project-without-data") is None
    assert MIG.legacy_bind_data(root, "") is None
    (tmp_path / "project" / "data").mkdir(parents=True)     # an empty ./data (docker made it) is not a ledger
    assert MIG.legacy_bind_data(root, tmp_path / "project") is None
