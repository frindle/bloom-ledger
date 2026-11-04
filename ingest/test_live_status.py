"""Live status: the Darkbloom key is stored privately and never echoed, /v1/live summarises Darkbloom + Sandbox from the
account API and watts from the Mac's newest power minute, and the page and settings render it. Fake data throughout."""
import json
import os
import sqlite3
import stat
import subprocess
from pathlib import Path

import bloom_accounting_index as AX
import bloom_accounting_live as LV
import bloom_accounting_page as PG
import dom_support as D

HERE = Path(__file__).resolve().parent
KEY = "dbk_test_0123456789abcdef"
PROVIDERS = {"providers": [{"nickname": "Studio", "online": True, "status": "online", "current_model": "m1",
                            "routing_eligibility": [{"model": "m0", "reason": "not_loaded"}, {"model": "m1", "reason": "eligible"}],
                            "pending_requests": 2, "max_concurrency": 24,
                            "system_metrics": {"thermal_state": "nominal", "cpu_usage": 0.1, "memory_pressure": 0.3},
                            "backend_capacity": {"slots": [{"performance_measurements": {"delivered_decode": {"tokens_per_second": 41.26}}}]}}]}
HOSTS = {"hosts": [{"name": "studio-sbx", "online": True, "state": "active", "mode": "accepting", "current_runs": 1}]}


def fake_get(table, calls=None):
    def get(url, key):
        if calls is not None:
            calls.append((url, key))
        return table.get(url, (500, None))
    return get


def db_with(rows):
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    for r in rows:
        db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, dbk_state, sandbox_jobs) VALUES (?,?,?,?,?,?)", r)
    return db


def setup_function(_):
    LV._cache.clear()


def test_saved_key_is_private_and_never_echoed(tmp_path):
    get = fake_get({LV.PROVIDERS_URL: (200, PROVIDERS), LV.SANDBOX_HOSTS_URL: (401, None)})
    code, obj = LV.key_post(tmp_path, json.dumps({"key": "  " + KEY + " "}).encode(), 1000, get)
    assert code == 200 and KEY not in json.dumps(obj)
    assert obj == {"set": True, "checked_at": 1000, "probe": {"darkbloom": 200, "sandbox": 401}}
    assert Path(LV.key_path(tmp_path)).read_text() == KEY
    assert stat.S_IMODE(os.stat(LV.key_path(tmp_path)).st_mode) == 0o600
    assert KEY not in json.dumps(LV.key_status(tmp_path))


def test_bad_keys_are_refused_and_null_removes(tmp_path):
    get = fake_get({})
    for bad in ("short", "has space in it", 12345, "x" * 513):
        assert LV.key_post(tmp_path, json.dumps({"key": bad}).encode(), 1, get)[0] == 400
    assert LV.key_post(tmp_path, b"not json", 1, get)[0] == 400
    assert not os.path.exists(LV.key_path(tmp_path))
    LV.key_post(tmp_path, json.dumps({"key": KEY}).encode(), 1, get)
    code, obj = LV.key_post(tmp_path, b'{"key": null}', 2, get)
    assert code == 200 and obj["set"] is False and not os.path.exists(LV.key_path(tmp_path))


def test_http_get_refuses_other_hosts_and_plain_http():
    assert LV.http_get_json("https://evil.example/v1/me/providers", KEY) == (0, None)
    assert LV.http_get_json("http://api.darkbloom.dev/v1/me/providers", KEY) == (0, None)


def test_live_summarises_darkbloom_sandbox_and_power(tmp_path):
    Path(LV.key_path(tmp_path)).parent.mkdir(parents=True)
    Path(LV.key_path(tmp_path)).write_text(KEY)
    db = db_with([("m4max", 900, 1.0, 60, "serving", 0), ("m4max", 960, 2.5, 60, "serving", 1)])
    calls = []
    get = fake_get({LV.PROVIDERS_URL: (200, PROVIDERS), LV.SANDBOX_HOSTS_URL: (200, HOSTS)}, calls)
    res = LV.live(tmp_path, LV.mac_view(db, 1000), 1000, get)
    (m,) = res["darkbloom"]["machines"]
    assert m["online"] and m["routing"] == "eligible" and m["decode_tps"] == 41.3 and m["pending"] == 2
    assert res["sandbox"]["hosts"][0]["running"] == 1
    assert res["mac"] == [{"machine_id": "m4max", "ts": 960, "age_s": 40, "stale": False, "watts": 150.0,
                           "darkbloom_state": "serving", "sandbox_jobs": 1}]
    assert all(k == KEY for _, k in calls) and len(calls) == 2
    LV.live(tmp_path, [], 1010, get)
    assert len(calls) == 2, "cached for CACHE_S"
    LV.live(tmp_path, [], 1000 + LV.CACHE_S, get)
    assert len(calls) == 4


def test_live_without_key_or_with_failures(tmp_path):
    res = LV.live(tmp_path, LV.mac_view(db_with([("m", 0, 1.0, 60, None, 0)]), 2000), 2000, fake_get({}))
    assert LV.mac_view(db_with([("m", 0, 1.0, 60, None, 0)]), 960)[0]["stale"] is False  # one 15-min batch late is normal
    assert res["darkbloom"] == {"error": "no API key saved"} and res["mac"][0]["stale"] is True
    Path(LV.key_path(tmp_path)).parent.mkdir(parents=True)
    Path(LV.key_path(tmp_path)).write_text(KEY)
    res = LV.live(tmp_path, [], 600, fake_get({LV.PROVIDERS_URL: (403, None), LV.SANDBOX_HOSTS_URL: (0, None)}))
    assert res["darkbloom"] == {"error": "Darkbloom doesn't accept API keys for this yet", "unsupported": True}
    assert res["sandbox"] == {"error": "Darkbloom unreachable"}
    calls = []
    def counting(url, key):
        calls.append(url)
        return (403, None)
    LV.live(tmp_path, [], 600 + LV.CACHE_S + 1, counting)
    assert LV.PROVIDERS_URL not in calls  # a rejected key is not re-asked for an hour


def run_home(tmp_path, live):
    page = tmp_path / "home.html"
    page.write_text(PG.render_page())
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps({"fetch": {"/v1/live": {"status": 200, "body": live}}, "steps": []}))
    res = subprocess.run(["node", str(HERE / "dom_harness.js"), str(page), str(sp)], capture_output=True, text=True, timeout=60,
                         env={k: v for k, v in os.environ.items() if k != "NODE_V8_COVERAGE"})
    assert res.returncode == 0 and res.stdout, res.stderr[-600:]
    out = json.loads(res.stdout)
    assert out["errors"] == [], out["errors"]
    return D.find(out["dom"], "live")["text"], D.find(out["dom"], "live-note")["text"]


def test_page_strip_shows_status_and_watts(tmp_path):
    live = {"darkbloom": LV.darkbloom_view(PROVIDERS), "sandbox": LV.sandbox_view(HOSTS),
            "mac": [{"machine_id": "m4max", "age_s": 40, "stale": False, "watts": 150.0, "sandbox_jobs": 1}]}
    text, note = run_home(tmp_path, live)
    assert "Studio: online, 2/24 requests, 41.3 tok/s" in text, text
    assert "studio-sbx: accepting, 1 running" in text and "150 W, 40 s ago" in text, text
    assert note == ""


def test_page_strip_without_key_falls_back_to_the_mac(tmp_path):
    live = {"darkbloom": {"error": "no API key saved"}, "sandbox": {"error": "no API key saved"},
            "mac": [{"machine_id": "m4max", "age_s": 400, "stale": True, "watts": None, "sandbox_jobs": 2}]}
    text, note = run_home(tmp_path, live)
    assert "m4max: 2 running (from the Mac)" in text and "not measured" in text and "stopped reporting" in text, text
    assert "Settings" in note


def test_settings_key_form_posts_and_shows_probe_without_the_key(tmp_path):
    st = {"set": True, "checked_at": 1793300000, "probe": {"darkbloom": 200, "sandbox": 403}}
    fx = {"/v1/settings": {"status": 200, "body": {"machines": [], "health": {"time": 1793300000}, "darkbloom_key": {"set": False}}},
          "POST /v1/settings/darkbloom-key": {"status": 200, "body": st}}
    res = D.run_page(tmp_path, fx, [{"do": "input", "id": "dbk-key", "values": {"dbk-key": KEY}},
                                    {"do": "submit", "id": "dbk-form"}])
    assert res["errors"] == [], res["errors"]
    (post,) = [f for f in res["fetches"] if f["method"] == "POST"]
    assert json.loads(post["body"]) == {"key": KEY}
    assert D.find(res["dom"], "dbk-key")["value"] == ""
    s = D.find(res["dom"], "dbk-status")["text"]
    assert "Darkbloom status: works" in s and "Sandbox status: key not accepted" in s and KEY not in s, s
