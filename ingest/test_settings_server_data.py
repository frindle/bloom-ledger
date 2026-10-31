"""Frozen test: server.py GET /v1/settings (machines, health, admin state; never a token hash)."""
import json

import bloom_settings as ST
import server as SV
from server_fixture import ADMIN, sha, web  # noqa: F401


def test_settings_data_shape_and_admin_state(web):
    status, ctype, body = web("GET", "/v1/settings")
    assert status == 200 and ctype == "application/json"
    data = json.loads(body)
    assert sorted(data) == ["admin_enabled", "health", "machines"] and data["admin_enabled"] is False
    assert [m["id"] for m in data["machines"]] == ["studio"] and data["machines"][0]["status"] == "not-reporting-yet"
    assert sorted(data["health"]) == ["data_bytes", "objects", "time", "version"]
    assert data["health"]["version"] == SV.Handler.server_version
    web.admin_file.write_text(ADMIN)
    assert json.loads(web("GET", "/v1/settings")[2])["admin_enabled"] is True


def test_settings_data_lists_registered_machines_and_hides_hashes(web):
    token = ST.add_machine(SV.MACHINES_PATH, "m1", 1.0)
    status, _, body = web("GET", "/v1/settings")
    assert [m["id"] for m in json.loads(body)["machines"]] == ["m1", "studio"]
    text = body.decode()
    assert sha("studio-token") not in text and sha(token) not in text and token not in text


def test_admin_secret_path_default():
    assert SV.ADMIN_PATH == "/run/secrets/bloom_admin"
