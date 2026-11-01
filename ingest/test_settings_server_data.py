"""Frozen test: server.py GET /v1/settings (machines, health; no admin state; never a token hash; profiles shown)."""
import json

import bloom_machine_profiles as MP
import bloom_settings as ST
import server as SV
from server_fixture import sha, web  # noqa: F401


def test_settings_data_shape_has_no_admin_state(web):
    status, ctype, body = web("GET", "/v1/settings")
    assert status == 200 and ctype == "application/json"
    data = json.loads(body)
    assert sorted(data) == ["health", "machines"], "no admin_enabled key: there is no admin key any more"
    assert [m["id"] for m in data["machines"]] == ["studio"] and data["machines"][0]["status"] == "not-reporting-yet"
    assert sorted(data["health"]) == ["data_bytes", "objects", "time", "version"]
    assert data["health"]["version"] == SV.Handler.server_version


def test_settings_data_lists_registered_machines_and_hides_hashes(web):
    token = ST.add_machine(SV.MACHINES_PATH, "m1", 1.0)
    status, _, body = web("GET", "/v1/settings")
    assert [m["id"] for m in json.loads(body)["machines"]] == ["m1", "studio"]
    text = body.decode()
    assert sha("studio-token") not in text and sha(token) not in text and token not in text


def test_settings_data_includes_saved_profiles(web):
    import bloom_ingest as I
    db = I.open_db(SV.ROOT / "index.sqlite")
    MP.upsert_profile(db, "studio", {"display_name": "Desk", "model": "Test-Model 1"}, 1)
    rows = {m["id"]: m for m in json.loads(web("GET", "/v1/settings")[2])["machines"]}
    assert rows["studio"]["profile"] == {"display_name": "Desk", "model": "Test-Model 1", "lease_start": None,
                                         "lease_monthly_cents": None, "acquisition": "leased"}
