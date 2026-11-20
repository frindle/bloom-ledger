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


def code_of():
    import server
    return AU.setup_code(server.ROOT)


def cookie_of(web):
    return web.last_headers["set-cookie"].split(";")[0]


def test_fresh_install_refuses_writes_until_setup(web):
    s, o = post(web, "/v1/settings/machines", {"id": "mac1"})
    assert s == 401 and o.get("setup") is True
    assert json.loads(web("GET", "/v1/auth/me")[2]) == {"logged_in": False, "mode": "setup"}


def test_setup_validates_input(web):
    assert post(web, "/v1/auth/setup", {"username": "me", "password": "short", "setup_code": code_of()})[0] == 400
    s, o = post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "timezone": "Nope/Zone", "setup_code": code_of()})
    assert s == 400 and "time zone" in o["error"]
    s, o = post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "rate": "abc", "setup_code": code_of()})
    assert s == 400 and "electricity" in o["error"]
    assert not AU.has_admin(web.db)


def test_setup_login_logout_and_protected_write(web):
    AU._fails.clear()
    s, _o = post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "timezone": "America/Chicago", "rate": "0.15", "bloomgauge": False, "setup_code": code_of()})
    assert s == 200
    assert "HttpOnly" in web.last_headers["set-cookie"] and "SameSite=Lax" in web.last_headers["set-cookie"]
    ck = cookie_of(web)
    assert post(web, "/v1/auth/setup", {"username": "x", "password": "longenough1", "setup_code": "whatever"})[0] == 409
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


def test_setup_always_needs_the_code_even_from_the_local_network(web):
    # 127.0.0.1 is as private as an address gets; it still gets no shortcut. Neither does a Tailscale/LAN peer.
    for extra in ({}, {"X-Forwarded-For": "8.8.8.8"}, {"X-Forwarded-For": "100.64.1.2"}, {"X-Forwarded-For": "192.168.1.9"}):
        AU._fails.clear()
        s, o = post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1"}, extra=extra)
        assert s == 403 and "setup code" in o["error"]
        s, _o = post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "setup_code": "wrong-code"}, extra=extra)
        assert s == 403
    assert not AU.has_admin(web.db)
    s, _o = post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "setup_code": code_of()})
    assert s == 200 and AU.has_admin(web.db)


def test_setup_code_is_rotated_after_use_and_guesses_lock_out(web):
    AU._fails.clear()
    old = code_of()
    for _ in range(5):
        assert post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "setup_code": "nope"})[0] == 403
    assert post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "setup_code": old})[0] == 429
    AU._fails.clear()
    assert post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "setup_code": old})[0] == 200
    assert code_of() != old


def test_setup_page_asks_for_the_code_and_says_where_it_is(web):
    page = web("GET", "/setup")[2].decode()
    assert 'id="code"' in page and "Setup code" in page and "docker compose logs" in page and "server.log" in page


def test_old_install_keeps_working_without_an_admin(web, monkeypatch):
    web.db.execute("CREATE TABLE IF NOT EXISTS acct_meta (k TEXT PRIMARY KEY, v TEXT)")
    web.db.execute("INSERT OR REPLACE INTO acct_meta VALUES ('migration_legacy_defaults_v1', '1')")
    web.db.commit()
    s, _o = post(web, "/v1/settings/machines", {"id": "oldmac"})
    assert s == 201          # same rule as before: private address plus same-origin


def _rows(web):
    return web.db.execute("SELECT key, effective_from, value_json FROM acct_settings ORDER BY rowid").fetchall()


def _migrated(web):
    import bloom_migrate as MIG
    web.db.execute("CREATE TABLE IF NOT EXISTS earnings (ledger_id TEXT, ts INTEGER, micro_usd INTEGER, kind TEXT, model TEXT,"
                   " job_id TEXT, completion_tokens INTEGER, source_machine TEXT)")
    web.db.execute("INSERT INTO earnings VALUES ('L1', 1791900000, 5, 'inference', 'm', 'j', 0, 'm1')")
    MIG.run(web.db, lambda m: None)


def test_setup_on_a_migrated_install_only_creates_the_admin(web):
    import bloom_accounting_config as CF
    _migrated(web)
    assert AU.auth_mode(web.db) == "lan"
    before = _rows(web)
    assert CF.effective_settings(web.db, "2026-11-01")["values"]["local_timezone"] == "America/Los_Angeles"
    page = web("GET", "/setup")[2].decode()
    assert 'id="code"' in page and 'id="tz"' not in page and "leaves them as they are" in page
    s, _o = post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "timezone": "Asia/Tokyo", "rate": "0.30",
                                         "setup_code": code_of()})
    assert s == 200 and AU.has_admin(web.db)
    assert _rows(web) == before     # no time zone, price or adder row written
    v = CF.effective_settings(web.db, "2026-11-01")["values"]
    assert v["local_timezone"] == "America/Los_Angeles" and CF.effective_settings(web.db, "2020-01-01")["values"]["local_timezone"] == "America/Los_Angeles"


def test_setup_with_a_time_zone_already_on_record_leaves_it_alone(web):
    import bloom_accounting_config as CF
    CF.set_setting(web.db, "local_timezone", "Europe/Berlin", "2026-01-01", 1)
    before = _rows(web)
    s, _o = post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "timezone": "Asia/Tokyo", "rate": "0.30",
                                         "setup_code": code_of()})
    assert s == 200 and _rows(web) == before
    assert CF.effective_settings(web.db, "2026-11-01")["values"]["local_timezone"] == "Europe/Berlin"


def test_fresh_install_setup_still_writes_its_choices(web):
    s, _o = post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "timezone": "Asia/Tokyo", "rate": "0.30",
                                         "setup_code": code_of()})
    assert s == 200
    assert {r[0] for r in _rows(web)} >= {"local_timezone", "rate_schedule"}


def test_optional_integration_switch(web):
    import bloom_integrations as IG
    assert IG.bloomgauge_state(web.db, {}) == "not set up"
    assert IG.bloomgauge_state(web.db, {"BLOOM_BLOOMGAUGE": "1"}) == "enabled"
    post(web, "/v1/auth/setup", {"username": "me", "password": "longenough1", "bloomgauge": True, "setup_code": code_of()})
    assert IG.bloomgauge_state(web.db, {}) == "enabled"
    assert json.loads(web("GET", "/v1/status")[2])["integrations"][0]["state"] == "enabled"
