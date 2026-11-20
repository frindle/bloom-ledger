"""Default machine id: installs that already hold data keep "m4max"; only a fresh install uses the host name."""
import importlib
import json
import socket

L = importlib.import_module("bloom_ledger")


def host(monkeypatch, name="Pennys-Mac.local"):
    monkeypatch.setattr(socket, "gethostname", lambda: name)


def test_fresh_install_uses_the_host_name(tmp_path, monkeypatch):
    host(monkeypatch)
    assert L.resolve_machine_id(tmp_path, env={}) == "Pennys-Mac"
    assert L.resolve_machine_id(tmp_path / "nothing-here", env={}) == "Pennys-Mac"


def test_existing_ledger_json_without_a_machine_id_keeps_m4max(tmp_path, monkeypatch):
    host(monkeypatch)
    (tmp_path / "ledger.json").write_text(json.dumps({"ingest_url": "http://10.0.0.5:8787"}))
    assert L.resolve_machine_id(tmp_path, env={}) == "m4max"
    (tmp_path / "ledger.json").write_text("not json")
    assert L.resolve_machine_id(tmp_path, env={}) == "m4max"


def test_existing_manifests_or_spool_keep_m4max(tmp_path, monkeypatch):
    host(monkeypatch)
    (tmp_path / "ledger").mkdir()
    assert L.resolve_machine_id(tmp_path, env={}) == "Pennys-Mac"          # an empty ledger folder is not data
    (tmp_path / "ledger" / "manifest-2026-11-01.json").write_text("{}")
    assert L.resolve_machine_id(tmp_path, env={}) == "m4max"
    other = tmp_path / "b"
    (other / "ledger-spool").mkdir(parents=True)
    assert L.resolve_machine_id(other, env={}) == "m4max"


def test_explicit_ids_always_win(tmp_path, monkeypatch):
    host(monkeypatch)
    (tmp_path / "ledger.json").write_text(json.dumps({"machine_id": "mac-mini"}))
    assert L.resolve_machine_id(tmp_path, env={}) == "mac-mini"
    assert L.resolve_machine_id(tmp_path, env={"BLOOM_MACHINE_ID": " from-env "}) == "from-env"
