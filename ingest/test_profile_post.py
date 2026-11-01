"""Frozen test: bloom_machine_profiles.profile_post (POST /v1/settings/machines/profile and /remove; synthetic values)."""
import json

import pytest

import bloom_ingest as I
import bloom_machine_profiles as MP
import bloom_settings as S

NOW = 1793300000.0
PROFILE = "/v1/settings/machines/profile"
REMOVE = "/v1/settings/machines/remove"


@pytest.fixture
def env(tmp_path):
    return I.open_db(tmp_path / "i.sqlite"), str(tmp_path / "machines.json")


def post(env, path, payload, raw=None):
    db, mp = env
    return MP.profile_post(path, raw if raw is not None else json.dumps(payload).encode(), db, mp, NOW)


def test_profile_saves_and_returns_the_stored_profile(env):
    code, obj = post(env, PROFILE, {"id": "m1", "display_name": " Desk ", "model": "Test-Model 1"})
    assert code == 200 and obj == {"id": "m1", "profile": {"display_name": "Desk", "model": "Test-Model 1",
                                                           "lease_start": None, "lease_monthly_cents": None, "acquisition": "leased", "active": True}}
    code, obj = post(env, PROFILE, {"id": "m1", "lease_start": "2026-03-01", "lease_monthly_cents": 100})
    assert code == 200 and obj["profile"]["display_name"] == "Desk" and obj["profile"]["lease_monthly_cents"] == 100
    assert MP.list_profiles(env[0])["m1"] == obj["profile"]


def test_bad_bodies_and_ids_are_400_and_write_nothing(env):
    for raw in (b"{nope", b"[1]", b'"x"', b"{}", b'{"id": "bad id"}', b'{"id": 5}', b'{"id": "-x"}'):
        for path in (PROFILE, REMOVE):
            assert post(env, path, None, raw=raw) == (400, {"error": "bad request"})
    assert MP.list_profiles(env[0]) == {}


def test_bad_fields_report_each_field(env):
    code, obj = post(env, PROFILE, {"id": "m1", "model": "", "lease_monthly_cents": 0, "extra": 1})
    assert code == 400 and obj["error"] == "bad fields"
    assert sorted(obj["fields"]) == ["extra", "lease_monthly_cents", "model"]
    assert MP.list_profiles(env[0]) == {}


def test_remove_revokes_the_token_and_keeps_the_profile_row(env):
    db, mp = env
    S.add_machine(mp, "m1", 1.0)
    post(env, PROFILE, {"id": "m1", "display_name": "Desk"})
    assert post(env, REMOVE, {"id": "m1"}) == (200, {"id": "m1", "removed": True})
    data = S.read_machines(mp)
    assert "m1" not in data["machines"] and data["revoked"] == ["m1"]
    assert MP.list_profiles(db)["m1"]["active"] is False and MP.list_profiles(db)["m1"]["display_name"] == "Desk"
    assert post(env, REMOVE, {"id": "never-seen"})[0] == 200
    assert MP.list_profiles(db)["never-seen"]["active"] is False


def test_unknown_path_is_404_before_the_body_is_read(env):
    assert post(env, "/v1/settings/machines/nope", None, raw=b"{nope") == (404, {"error": "not found"})
    assert post(env, "/v1/settings/machines", {"id": "m1"}) == (404, {"error": "not found"})
