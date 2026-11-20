"""First run, setup, login, write protection and status, through a real server with the default (login on) mode. Fake data."""
import json

import bloom_auth as AU
from server_fixture import web  # noqa: F401

H = {"Content-Type": "application/json", "Host": "127.0.0.1:1", "Origin": "http://127.0.0.1:1"}


def post(web, path, obj, cookie=None, extra=None):
    h = dict(H)
    if cookie:
        h["Cookie"] = cookie
    h.update(extra or {})
    s, _c, body = web("POST", path, body=json.dumps(obj).encode(), headers=h)
    return s, json.loads(body or b"{}")


def cookie_of(web):
    return web.last_headers["set-cookie"].split(";")[0]


def test_fresh_install_refuses_writes_until_setup(web):
    s, o = post(web, "/v1/settings/machines", {"id": "mac1"})
    assert s == 401 and o.get("setup") is True
    assert json.loads(web("GET", "/v1/auth/me")[2]) == {"logged_in": False, "mode": "setup"}


def test_setup_validates_input(web):
    assert post(web, "/v1/auth/setup", {"username": "me", "password": "short"})[0] == 400
    s, o = post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "timezone": "Nope/Zone"})
    assert s == 400 and "time zone" in o["error"]
    s, o = post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "rate": "abc"})
    assert s == 400 and "electricity" in o["error"]
    assert not AU.has_admin(web.db)


def test_setup_login_logout_and_protected_write(web):
    AU._fails.clear()
    s, _o = post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "timezone": "America/Chicago", "rate": "0.15", "bloomgauge": False})
    assert s == 200
    assert "HttpOnly" in web.last_headers["set-cookie"] and "SameSite=Lax" in web.last_headers["set-cookie"]
    ck = cookie_of(web)
    assert post(web, "/v1/auth/setup", {"username": "x", "password": "longenough1"})[0] == 409
    # settings applied
    import bloom_accounting_config as CF
    v = CF.effective_settings(web.db, "2026-11-01")["values"]
    assert v["local_timezone"] == "America/Chicago" and v["rate_schedule"][0]["periods"][0]["rate"] == "0.15"
    # a write without the cookie is refused, with it it works
    s, o = post(web, "/v1/settings/machines", {"id": "mac1"})
    assert s == 401 and o.get("login") is True
    s, o = post(web, "/v1/settings/machines", {"id": "mac1"}, cookie=ck)
    assert s == 201 and o["pair_code"]
    # cross-origin with a valid cookie is refused
    s, _o = post(web, "/v1/settings/machines", {"id": "mac2"}, cookie=ck, extra={"Origin": "http://evil.example"})
    assert s == 403
    # logout kills the session
    assert post(web, "/v1/auth/logout", {}, cookie=ck)[0] == 200
    assert post(web, "/v1/settings/machines", {"id": "mac3"}, cookie=ck)[0] == 401
    # login
    assert post(web, "/v1/auth/login", {"username": "me", "password": "wrongwrong"})[0] == 401
    assert post(web, "/v1/auth/login", {"username": "me", "password": "longenough1"})[0] == 200
    ck2 = cookie_of(web)
    assert post(web, "/v1/settings/machines", {"id": "mac3"}, cookie=ck2)[0] == 201


def test_login_lockout(web):
    AU._fails.clear()
    AU.create_admin(web.db, "me", "longenough1")
    for _ in range(5):
        assert post(web, "/v1/auth/login", {"username": "me", "password": "wrongwrong"})[0] == 401
    assert post(web, "/v1/auth/login", {"username": "me", "password": "longenough1"})[0] == 429
    AU._fails.clear()


def test_reads_stay_open_and_status_has_the_shape(web):
    s, _c, body = web("GET", "/v1/status")
    d = json.loads(body)
    assert s == 200 and len(d["machines"]) == 1 and d["machines"][0]["days_sealed"] == 0 and "nothing received" in d["machines"][0]["hint"].lower()
    assert d["integrations"][0] == {"name": "BloomGauge", "optional": True, "state": "not set up",
                                    "detail": "Not needed. The ledger reads Darkbloom directly."}
    for p in ("/", "/status", "/setup", "/login", "/settings", "/log", "/tax"):
        assert web("GET", p)[0] == 200, p
    assert web("GET", "/static/bloom.css")[0] == 200 and web("GET", "/static/../server.py")[0] == 404


def test_whoami_checks_the_machine_token(web):
    assert web("GET", "/v1/whoami", token="mac1-token")[0] == 200
    assert web("GET", "/v1/whoami", token="wrong")[0] == 401
    assert web("GET", "/v1/whoami")[0] == 401


def test_setup_code_required_off_the_local_network(web):
    s, o = post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1"}, extra={"X-Forwarded-For": "8.8.8.8"})
    assert s == 403 and "setup code" in o["error"]
    code = AU.setup_code(web.db and __import__("server").ROOT)
    s, _o = post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "setup_code": code}, extra={"X-Forwarded-For": "8.8.8.8"})
    assert s == 200


def test_old_install_keeps_working_without_an_admin(web, monkeypatch):
    web.db.execute("CREATE TABLE IF NOT EXISTS acct_meta (k TEXT PRIMARY KEY, v TEXT)")
    web.db.execute("INSERT OR REPLACE INTO acct_meta VALUES ('migration_legacy_defaults_v1', '1')")
    web.db.commit()
    s, _o = post(web, "/v1/settings/machines", {"id": "oldmac"})
    assert s == 201          # same rule as before: private address plus same-origin


def test_optional_integration_switch(web):
    import bloom_integrations as IG
    assert IG.bloomgauge_state(web.db, {}) == "not set up"
    assert IG.bloomgauge_state(web.db, {"BLOOM_BLOOMGAUGE": "1"}) == "enabled"
    post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "bloomgauge": True})
    assert IG.bloomgauge_state(web.db, {}) == "enabled"
    assert json.loads(web("GET", "/v1/status")[2])["integrations"][0]["state"] == "enabled"
