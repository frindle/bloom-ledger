"""Frozen test: server.py serves GET /settings and the ingest endpoint honours the dynamic machines.json."""
from pathlib import Path

import bloom_settings as ST
import server as SV
from server_fixture import ADMIN, post_object, sha, web  # noqa: F401


def test_settings_page_is_served(web):
    status, ctype, body = web("GET", "/settings")
    assert status == 200 and ctype.startswith("text/html"), (status, ctype)
    assert body == (Path(SV.__file__).resolve().parent / "settings.html").read_bytes()


def test_ingest_accepts_tokens_from_machines_json(web):
    assert post_object(web, "unknown-token") == 401
    token = ST.add_machine(SV.MACHINES_PATH, "m1", 1.0)
    assert post_object(web, token) == 201, "a machine added to machines.json can ingest without a restart"
    assert post_object(web, "studio-token") == 201, "the secret file still works"


def test_revoked_ids_are_cut_off_including_secret_file_machines(web):
    token = ST.add_machine(SV.MACHINES_PATH, "m1", 1.0)
    ST.revoke_machine(SV.MACHINES_PATH, "m1")
    ST.revoke_machine(SV.MACHINES_PATH, "studio")
    assert post_object(web, token) == 401
    assert post_object(web, "studio-token") == 401


def test_machines_file_defaults_next_to_the_data_dir():
    assert SV.MACHINES_PATH.endswith("machines.json") and Path(SV.SETTINGS).name == "settings.html"
