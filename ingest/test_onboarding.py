"""Plug-and-play onboarding and write-off rules: pairing codes, the installer and client bundle, per-Mac Darkbloom keys,
the write_off setting and the settings page controls. Fake data throughout."""
import importlib.util
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

import bloom_accounting_live as LV
import bloom_accounting_writeoff as WO
import bloom_pairing as PA
import dom_support as D
import server as SV
from server_fixture import web  # noqa: F401

HERE = Path(__file__).resolve().parent
KEY = "dbk_test_0123456789abcdef"
KEY2 = "dbk_test_fedcba9876543210"
SAME = {"Host": "ledger.test:8787", "Origin": "http://ledger.test:8787", "Content-Type": "application/json"}


def setup_function(_):
    PA._codes.clear()
    LV._cache.clear()


# --- write-off rules ---------------------------------------------------------------------------------------------

def test_defaults_keep_the_original_behaviour():
    r = WO.rules(None)
    assert r == WO.rules({"write_off": "junk"}) == {"count": {"darkbloom": True, "sandbox": True, "own": False, "idle": False},
                                                    "power": "work_minutes", "share": "measured", "fixed_pct": None, "lease_pct": 100}
    assert [WO.minute_counts(r, s, "serving") for s in ("gpu", "sandbox", "other", "idle", "gap")] == [True, True, False, False, False]


def test_toggles_change_what_counts():
    r = WO.rules({"write_off": {"count": {"darkbloom": False, "own": True, "idle": True}}})
    assert not WO.minute_counts(r, "gpu", "serving") and WO.minute_counts(r, "sandbox", None)
    assert WO.minute_counts(r, "other", "off")
    assert WO.minute_counts(r, "idle", "idle") and WO.minute_counts(r, "idle", "serving")
    assert not WO.minute_counts(r, "idle", "off") and not WO.minute_counts(r, "idle", None), "idle counts only while online"


def test_power_share_and_lease_methods():
    t = {"cost_micro": 10_000, "business_cost_micro": 3_000, "business_bp": 2500}
    base = {"count": {}}
    assert WO.power_business_micro(WO.rules({"write_off": base}), t) == 3_000
    assert WO.power_business_micro(WO.rules({"write_off": dict(base, power="all")}), t) == 10_000
    assert WO.power_business_micro(WO.rules({"write_off": dict(base, power="none")}), t) == 0
    assert WO.power_business_micro(WO.rules({"write_off": dict(base, power="share_of_total")}), t) == 2_500
    fixed = WO.rules({"write_off": dict(base, power="share_of_total", share="fixed", fixed_pct=60)})
    assert WO.share_bp(fixed, 2500) == 6000 and WO.power_business_micro(fixed, t) == 6_000
    assert WO.power_business_micro(fixed, {"cost_micro": None}) is None
    assert WO.lease_business_cents(WO.rules({"write_off": {"lease_pct": 50}}), 120_000) == 60_000
    assert WO.lease_business_cents(WO.rules(None), None) is None
    assert WO.rules({"write_off": {"share": "fixed"}})["share"] == "measured", "a fixed share without a percent is ignored"


def test_validate_names_each_problem():
    assert WO.validate({"count": {"own": True}, "power": "all", "lease_pct": 80}) == []
    errs = WO.validate({"count": {"own": "yes", "pets": True}, "power": "most", "share": "fixed", "lease_pct": 101, "x": 1})
    text = "; ".join(errs)
    for frag in ("unknown write_off fields: x", "count must", "power must", "fixed share needs", "lease_pct must"):
        assert frag in text, text
    assert WO.validate([1]) == ["write_off must be an object"]
    assert len(WO.describe(WO.rules(None))) == 4 and "your own local work" not in WO.describe(WO.rules(None))[0]


def test_write_off_setting_is_validated_and_shown(web):
    bad = json.dumps({"key": "write_off", "value": {"power": "most"}, "effective_from": "2026-01-01"}).encode()
    status, _, body = web("POST", "/v1/accounting/settings", bad, headers=SAME)
    assert status == 400 and "power must" in json.loads(body)["error"]
    good = {"count": {"own": True, "darkbloom": False}, "power": "all", "share": "fixed", "fixed_pct": 75, "lease_pct": 40}
    status, _, _ = web("POST", "/v1/accounting/settings",
                       json.dumps({"key": "write_off", "value": good, "effective_from": "2000-01-01"}).encode(), headers=SAME)
    assert status == 200
    wo = json.loads(web("GET", "/v1/settings")[2])["write_off"]
    assert wo["count"] == {"darkbloom": False, "sandbox": True, "own": True, "idle": False}
    assert (wo["power"], wo["share"], wo["fixed_pct"], wo["lease_pct"]) == ("all", "fixed", 75, 40)


# --- pairing -----------------------------------------------------------------------------------------------------

def test_codes_are_single_use_expire_and_replace_older_ones():
    sid = "a" * 32
    c1 = PA.new_code("m1", "tok-1", 1000)
    c2 = PA.new_code("m1", "tok-2", 1001)
    assert PA.redeem(json.dumps({"code": c1}).encode(), 1002, sid)[0] == 404, "a newer code replaces the old one"
    assert PA.redeem(json.dumps({"code": c2}).encode(), 1002, sid) == (200, {"machine_id": "m1", "token": "tok-2", "server_id": sid})
    assert PA.redeem(json.dumps({"code": c2}).encode(), 1003, sid)[0] == 404, "single use"
    c3 = PA.new_code("m2", "tok-3", 1000)
    assert PA.redeem(json.dumps({"code": c3}).encode(), 1000 + PA.PAIR_TTL_S, sid)[0] == 404, "expired"
    assert PA.redeem(b"nope", 1, sid)[0] == 400 and PA.redeem(b'{"code": "a b"}', 1, sid)[0] == 400


def test_server_id_is_stable(tmp_path):
    a = PA.server_id(tmp_path)
    assert len(a) == 32 and PA.server_id(tmp_path) == a


def test_add_machine_with_key_pairs_and_redeems_over_http(web):
    body = json.dumps({"id": "mini", "darkbloom_key": KEY}).encode()
    status, _, raw = web("POST", "/v1/settings/machines", body, headers=SAME)
    reply = json.loads(raw)
    assert status in (200, 201) and reply["darkbloom_key_saved"] is True and reply["pair_ttl_s"] == PA.PAIR_TTL_S
    assert KEY not in raw.decode() and LV.read_machine_keys(SV.ROOT) == {"mini": KEY}
    status, _, raw = web("POST", "/v1/pair", json.dumps({"code": reply["pair_code"]}).encode())
    paired = json.loads(raw)
    assert status == 200 and paired["machine_id"] == "mini" and paired["token"] == reply["token"]
    assert paired["server_id"] == json.loads(web("GET", "/v1/hello")[2])["server_id"]
    assert web("POST", "/v1/pair", json.dumps({"code": reply["pair_code"]}).encode())[0] == 404
    status, _, _ = web("POST", "/v1/settings/machines/remove", json.dumps({"id": "mini"}).encode(), headers=SAME)
    assert status == 200 and LV.read_machine_keys(SV.ROOT) == {}


def test_bad_key_is_refused_before_the_machine_is_added(web):
    status, _, raw = web("POST", "/v1/settings/machines", json.dumps({"id": "m9", "darkbloom_key": "x y"}).encode(), headers=SAME)
    assert status == 400 and "m9" not in [m["id"] for m in json.loads(web("GET", "/v1/settings")[2])["machines"]]


def test_pair_is_lan_only(web):
    import time
    code = PA.new_code("m1", "tok-1", time.time())
    for h in ({"CF-Connecting-IP": "1.2.3.4"}, {"X-Forwarded-For": "8.8.8.8"}):
        assert web("POST", "/v1/pair", json.dumps({"code": code}).encode(), headers=h)[0] == 403
    assert web("POST", "/v1/pair", b"x" * 2000)[0] == 413


def test_installer_gets_this_ledgers_address(web):
    status, ctype, raw = web("GET", "/install.sh", headers={"Host": "10.0.0.5:8787"})
    text = raw.decode()
    assert status == 200 and ctype.startswith("text/x-shellscript")
    assert 'BASE="http://10.0.0.5:8787"' in text and "@@LEDGER_BASE@@" not in text
    assert web("GET", "/install.sh", headers={"Host": "evil\"; rm -rf ~"})[0] == 400
    assert PA.install_script("a b") is None and PA.install_script("[::1]:8787").startswith("#!/bin/sh")


def test_installer_is_valid_sh_and_keeps_the_token_off_the_command_line():
    src = (PA.CLIENT_DIR / "install.sh").read_text()
    assert subprocess.run(["sh", "-n", str(PA.CLIENT_DIR / "install.sh")]).returncode == 0
    assert '"/usr/bin/security", "-i"' in src and "-w \"$TOKEN\"" not in src
    for job in ("power", "archive", "ship", "manifest", "find", "earnings"):
        assert job in src.split("JOBS=")[1].split("\n")[0]


def test_bundle_is_deterministic_and_complete():
    a, b = PA.client_bundle(), PA.client_bundle()
    assert a == b
    names = tarfile.open(fileobj=io.BytesIO(a)).getnames()
    for f in ("install.sh", "bloom-power-log.py", "bloom-archive.py", "bloom-ship.py", "bloom-find.py", "bloom_archive.py",
              "bloom_ship.py", *PA.LIB_FILES):
        assert "bloom-ledger-client/" + f in names, f
    assert not [n for n in names if "__pycache__" in n or "/." in n]
    assert len(PA.client_version()) == 12


def test_bundled_python_parses_as_python_39():
    import ast
    for name, p in PA.client_files():
        if name.endswith(".py"):
            ast.parse(p.read_text(), feature_version=(3, 9))
    for name, p in PA.client_files():
        assert "/Users/" not in p.read_text(), name


def _find():
    spec = importlib.util.spec_from_file_location("bloom_find", PA.CLIENT_DIR / "bloom-find.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_find_moves_to_the_ledger_with_the_same_server_id(tmp_path):
    F = _find()
    import ipaddress
    sid = "b" * 32
    (tmp_path / "ledger.json").write_text(json.dumps({"machine_id": "m1", "ingest_url": "http://10.9.9.1:8787", "server_id": sid}))
    answers = {"http://10.9.9.7:8787": sid, "http://10.9.9.8:8787": "c" * 32}
    probe = lambda base: answers.get(base)  # noqa: E731
    assert F.run(tmp_path, probe, [ipaddress.ip_network("10.9.9.0/24")]) == "moved"
    cfg = json.loads((tmp_path / "ledger.json").read_text())
    assert cfg == {"machine_id": "m1", "ingest_url": "http://10.9.9.7:8787", "server_id": sid}
    assert F.run(tmp_path, probe, [ipaddress.ip_network("10.9.9.0/24")]) == "ok"
    answers["http://10.9.9.9:8787"] = sid
    answers.pop("http://10.9.9.7:8787")
    answers["http://10.9.9.10:8787"] = sid
    assert F.run(tmp_path, probe, [ipaddress.ip_network("10.9.9.0/24")]) == "ambiguous"
    assert json.loads((tmp_path / "ledger.json").read_text())["ingest_url"] == "http://10.9.9.7:8787"
    (tmp_path / "ledger.json").write_text("{}")
    assert F.run(tmp_path, probe, []) == "not-paired"


def test_find_only_scans_private_networks():
    F = _find()
    text = "inet 127.0.0.1 netmask\ninet 169.254.3.3 x\ninet 8.8.8.8 x\ninet 192.168.1.20 netmask\ninet 192.168.1.30 x"
    assert [str(n) for n in F.local_networks(text)] == ["192.168.1.0/24"]


# --- multiple Darkbloom accounts -----------------------------------------------------------------------------------

def test_live_merges_every_saved_key(tmp_path):
    Path(LV.key_path(tmp_path)).parent.mkdir(parents=True)
    Path(LV.key_path(tmp_path)).write_text(KEY)
    LV.set_machine_key(tmp_path, "mini", KEY2)
    LV.set_machine_key(tmp_path, "dup", KEY)
    assert LV.all_keys(tmp_path) == [KEY, KEY2]
    assert oct(os.stat(LV.machine_keys_path(tmp_path)).st_mode & 0o777) == "0o600"
    prov = {KEY: {"providers": [{"nickname": "Studio", "online": True}]},
            KEY2: {"providers": [{"nickname": "Mini", "online": False}]}}
    calls = []

    def get(url, key):
        calls.append(key)
        if url == LV.PROVIDERS_URL:
            return 200, prov[key]
        return (500, None) if key == KEY2 else (200, {"hosts": [{"name": "sbx", "online": True}]})
    res = LV.live(tmp_path, [], 1000, get)
    assert sorted(m["name"] for m in res["darkbloom"]["machines"]) == ["Mini", "Studio"]
    assert "error" not in res["sandbox"], "one key working is enough"
    assert set(calls) == {KEY, KEY2}


# --- settings page -----------------------------------------------------------------------------------------------

SETTINGS = {"machines": [], "health": {"time": 1793300000}, "darkbloom_key": {"set": False},
            "write_off": WO.rules(None)}


def test_settings_page_shows_rules_and_saves_them(tmp_path):
    fx = {"/v1/settings": {"status": 200, "body": SETTINGS},
          "POST /v1/accounting/settings": {"status": 200, "body": {"ok": True}}}
    res = D.run_page(tmp_path, fx, [
        {"do": "change", "id": "wo-own", "values": {"wo-own": "yes", "wo-darkbloom": "no", "wo-power": "share_of_total",
                                                    "wo-share": "fixed", "wo-fixed": "62.5", "wo-lease": "50",
                                                    "wo-from": "2026-07-01"}},
        {"do": "submit", "id": "wo-form"}])
    assert res["errors"] == [], res["errors"]
    (post,) = [f for f in res["fetches"] if f["method"] == "POST"]
    assert post["url"] == "/v1/accounting/settings"
    assert json.loads(post["body"]) == {"key": "write_off", "effective_from": "2026-07-01", "value": {
        "count": {"darkbloom": False, "sandbox": True, "own": True, "idle": False},
        "power": "share_of_total", "share": "fixed", "fixed_pct": 62.5, "lease_pct": 50}}
    assert "Saved" in D.find(res["dom"], "wo-status")["text"]
    assert "62.5% (fixed)" in D.find(res["dom"], "wo-summary")["text"]
    assert [f["url"] for f in res["fetches"] if f["method"] == "GET"] == ["/v1/settings"]


def test_settings_page_renders_saved_rules_and_refuses_bad_percent(tmp_path):
    saved = dict(SETTINGS, write_off=WO.rules({"write_off": {"count": {"idle": True}, "power": "none", "lease_pct": 30}}))
    res = D.run_page(tmp_path, {"/v1/settings": {"status": 200, "body": saved}},
                     [{"do": "input", "id": "wo-lease", "values": {"wo-lease": "130"}}, {"do": "submit", "id": "wo-form"}])
    assert D.find(res["dom"], "wo-idle")["value"] == "yes" and D.find(res["dom"], "wo-power")["value"] == "none"
    assert D.find(res["dom"], "wo-fixed")["disabled"] is True
    assert "between 0 and 100" in D.find(res["dom"], "wo-error")["text"]
    assert not [f for f in res["fetches"] if f["method"] == "POST"]


def test_add_machine_sends_the_key_and_shows_the_install_command(tmp_path):
    reply = {"id": "mini", "token": "tok-abc", "pair_code": "CODE_abcdefghij", "pair_ttl_s": 1800, "darkbloom_key_saved": True}
    fx = {"/v1/settings": {"status": 200, "body": SETTINGS}, "POST /v1/settings/machines": {"status": 201, "body": reply}}
    res = D.run_page(tmp_path, fx, [{"do": "submit", "id": "add-form", "values": {"new-id": "mini", "new-dbk": KEY}},
                                    {"do": "click", "id": "pair-copy"}])
    assert res["errors"] == [], res["errors"]
    (post,) = [f for f in res["fetches"] if f["method"] == "POST"]
    assert json.loads(post["body"]) == {"id": "mini", "darkbloom_key": KEY}
    cmd = "curl -fsSL http://10.0.12.46:8787/install.sh | sh -s -- --pair CODE_abcdefghij"
    assert D.find(res["dom"], "pair-cmd")["text"] == cmd and res["clipboard"] == [cmd]
    assert D.find(res["dom"], "pair-box")["hidden"] is False and D.find(res["dom"], "new-dbk")["value"] == ""
    assert "30 minutes" in D.find(res["dom"], "pair-ttl")["text"] and "key is saved" in D.find(res["dom"], "pair-note")["text"]
    assert KEY not in json.dumps(res["dom"])


def test_install_command_warns_on_a_public_hostname(tmp_path):
    reply = {"id": "m", "token": "t", "pair_code": "CODE_abcdefghij", "pair_ttl_s": 1800, "darkbloom_key_saved": False}
    fx = {"/v1/settings": {"status": 200, "body": SETTINGS}, "POST /v1/settings/machines": {"status": 201, "body": reply}}
    res = D.run_page(tmp_path, fx, [{"do": "submit", "id": "add-form", "values": {"new-id": "m"}}], origin="https://ledger.example.com")
    (post,) = [f for f in res["fetches"] if f["method"] == "POST"]
    assert json.loads(post["body"]) == {"id": "m"}
    assert "local network address" in D.find(res["dom"], "pair-note")["text"]
