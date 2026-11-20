"""Install command and script always use a private-IP ledger address; install.sh refuses anything else before pairing and
retries launchctl bootstrap. Fake data."""
import re
import subprocess
from pathlib import Path

import pytest

import bloom_pairing as PA

INSTALL = PA.CLIENT_DIR / "install.sh"
MSG = PA.NO_LAN_MESSAGE


@pytest.mark.parametrize("host", ["10.0.0.5", "10.255.1.1", "172.16.0.1", "172.31.9.9", "192.168.1.20", "100.64.0.7", "100.127.255.1", "127.0.0.1"])
def test_private_ipv4_accepted(host):
    assert PA.private_ipv4(host)


@pytest.mark.parametrize("host", ["ledger.example.com", "8.8.8.8", "172.15.0.1", "172.32.0.1", "192.169.0.1", "100.128.0.1", "11.0.0.1",
                                  "::1", "10.0.0", "10.0.0.256", "", "10.0.0.1.example.com"])
def test_other_hosts_refused(host):
    assert not PA.private_ipv4(host)


def test_ledger_base_prefers_a_private_host_header_then_the_setting():
    assert PA.ledger_base("192.168.1.20:8787", None) == "http://192.168.1.20:8787"
    assert PA.ledger_base("192.168.1.20:8787", "http://10.0.0.9:8787") == "http://192.168.1.20:8787"
    assert PA.ledger_base("ledger.example.com", "http://10.0.0.9:8787") == "http://10.0.0.9:8787"
    assert PA.ledger_base("ledger.example.com", "10.0.0.9:8787/") == "http://10.0.0.9:8787"
    assert PA.ledger_base("ledger.example.com", None) == "http://ledger.example.com"       # a hostname is fine
    assert PA.ledger_base("ledger.example.com", "https://mac.tail1234.ts.net") == "https://mac.tail1234.ts.net"
    assert PA.ledger_base("ledger.example.com", "http://100.100.1.2:8787") == "http://100.100.1.2:8787"   # Tailscale
    assert PA.ledger_base("8.8.8.8:8787", None) is None                                    # a public IP literal is not
    assert PA.ledger_base("8.8.8.8", "http://8.8.8.8:8787") is None
    assert PA.ledger_base(None, "http://10.0.0.9:8787") == "http://10.0.0.9:8787"


def test_install_script_never_carries_the_public_name():
    text = PA.install_script("ledger.example.com", lan_url="http://10.0.0.9:8787")
    assert 'BASE="http://10.0.0.9:8787"' in text and "ledger.example.com" not in text and "@@LEDGER_BASE@@" not in text
    assert 'BASE="http://192.168.1.20:8787"' in PA.install_script("192.168.1.20:8787", lan_url="http://10.0.0.9:8787")


def test_install_script_without_any_private_address_explains_itself():
    text = PA.install_script("8.8.8.8:8787")
    assert text.startswith("#!/bin/sh") and "BLOOM_LEDGER_LAN_URL" in text and "exit 1" in text and "BASE=" not in text
    r = subprocess.run(["sh", "-c", text], capture_output=True, text=True)
    assert r.returncode == 1 and "BLOOM_LEDGER_LAN_URL" in r.stderr
    assert PA.install_script("bad host") is None


def shell_function(name):
    src = INSTALL.read_text()
    m = re.search(r"^%s\(\) \{\n.*?^\}\n" % name, src, re.S | re.M)
    assert m, name
    return m.group(0)


@pytest.mark.parametrize("host,ok", [("192.168.1.20", True), ("10.1.2.3", True), ("172.20.0.1", True), ("172.15.0.1", False),
                                     ("172.32.0.1", False), ("ledger.example.com", True), ("my-mac.local", True), ("8.8.8.8", False), ("192.169.1.1", False),
                                     ("100.64.9.9", True), ("127.0.0.1", True), ("", False)])
def test_install_sh_ip_check(host, ok):
    r = subprocess.run(["sh", "-c", shell_function("acceptable_host") + '\nacceptable_host "$1"', "sh", host])
    assert (r.returncode == 0) is ok


def test_install_sh_checks_the_address_before_pairing_and_names_the_lan_url():
    src = INSTALL.read_text()
    check = src.index('acceptable_host "$BASE_HOST" || die')
    assert check < src.index('say "pairing"') and check < src.index("/v1/hello") and check < src.index("/v1/pair")
    assert "LAN address" in src[check:check + 400]
    assert subprocess.run(["bash", "-n", str(INSTALL)]).returncode == 0 and subprocess.run(["sh", "-n", str(INSTALL)]).returncode == 0


def test_install_sh_refuses_a_public_base_without_contacting_it(tmp_path):
    # run the real script with a public BASE; stub uname/id so the early checks pass, and curl/launchctl to record any use
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "calls"
    for name, body in (("uname", 'echo Darwin'), ("id", 'echo 501'), ("curl", 'echo curl >> "%s"; exit 1' % log),
                       ("launchctl", 'echo launchctl >> "%s"' % log)):
        (bindir / name).write_text("#!/bin/sh\n" + body + "\n")
        (bindir / name).chmod(0o755)
    script = tmp_path / "install.sh"
    script.write_text(INSTALL.read_text().replace("@@LEDGER_BASE@@", "http://8.8.8.8"))
    r = subprocess.run(["sh", str(script), "--pair", "ABCDEFGHIJKL123"], capture_output=True, text=True,
                       env={"PATH": "%s:/usr/bin:/bin" % bindir, "HOME": str(tmp_path)})
    assert r.returncode == 1 and "not a private address" in r.stderr and "8.8.8.8" in r.stderr
    assert not log.exists()


def test_launchctl_bootstrap_is_retried_five_times_one_second_apart(tmp_path):
    src = INSTALL.read_text()
    m = re.search(r"  n=0\n  until launchctl bootstrap.*?  done\n", src, re.S)
    assert m and "sleep 1" in m.group(0) and "-lt 5" in m.group(0)
    snippet = "\n".join(l[2:] if l.startswith("  ") else l for l in m.group(0).splitlines())

    def run(fail_times):
        state = tmp_path / ("s%d" % fail_times)
        state.write_text("0")
        prog = ('set -eu\ndie() { echo "DIE $*" >&2; exit 1; }\nsleep() { echo slept >> "%s.sleeps"; }\n'
                'launchctl() { n=$(cat "%s"); echo $((n + 1)) > "%s"; [ "$n" -ge %d ]; }\n'
                'UID_NUM=1 f=x PREFIX=p job=j\n%s\n') % (state, state, state, fail_times, snippet)
        r = subprocess.run(["sh", "-c", prog], capture_output=True, text=True)
        sleeps = Path(str(state) + ".sleeps")
        return r, (len(sleeps.read_text().split()) if sleeps.exists() else 0), int(state.read_text())
    r, slept, calls = run(0)
    assert r.returncode == 0 and slept == 0 and calls == 1
    r, slept, calls = run(3)
    assert r.returncode == 0 and slept == 3 and calls == 4
    r, slept, calls = run(4)
    assert r.returncode == 0 and calls == 5
    r, slept, calls = run(9)
    assert r.returncode == 1 and "DIE could not load" in r.stderr and calls == 5 and slept == 4


# --- through the server and the Settings page -------------------------------------------------------------------------
import json

import dom_support as D
import server as SV
from server_fixture import web  # noqa: F401,E402

_REPLY = {"id": "m", "token": "t", "pair_code": "CODE_abcdefghij", "pair_ttl_s": 1800, "darkbloom_key_saved": False}


def test_public_host_gets_the_lan_url_from_the_setting(web, monkeypatch):
    monkeypatch.setattr(SV, "LAN_URL", "http://10.0.0.9:8787", raising=False)
    status, _ctype, raw = web("GET", "/install.sh", headers={"Host": "ledger.example.com"})
    assert status == 200 and 'BASE="http://10.0.0.9:8787"' in raw.decode() and "ledger.example.com" not in raw.decode()
    assert json.loads(web("GET", "/v1/settings", headers={"Host": "ledger.example.com"})[2])["lan_url"] == "http://10.0.0.9:8787"
    assert json.loads(web("GET", "/v1/settings", headers={"Host": "192.168.1.20:8787"})[2])["lan_url"] == "http://192.168.1.20:8787"


def test_public_host_without_a_setting_gets_a_clear_message_not_a_broken_script(web, monkeypatch):
    monkeypatch.setattr(SV, "LAN_URL", "", raising=False)
    status, _ctype, raw = web("GET", "/install.sh", headers={"Host": "8.8.8.8:8787"})
    assert status == 200 and b"BLOOM_LEDGER_LAN_URL" in raw and b"BASE=" not in raw
    assert json.loads(web("GET", "/v1/settings", headers={"Host": "8.8.8.8:8787"})[2])["lan_url"] is None


def _page(tmp_path, lan_url, origin):
    body = {"machines": [], "health": {"time": 1793300000}, "darkbloom_key": {"set": False}, "write_off": {}, "lan_url": lan_url}
    fx = {"/v1/settings": {"status": 200, "body": body}, "POST /v1/settings/machines": {"status": 201, "body": _REPLY}}
    res = D.run_page(tmp_path, fx, [{"do": "submit", "id": "add-form", "values": {"new-id": "m"}}], origin=origin)
    assert res["errors"] == [], res["errors"]
    return D.find(res["dom"], "pair-cmd")["text"], D.find(res["dom"], "pair-note")["text"]


def test_settings_page_builds_the_command_from_the_lan_url_on_a_public_origin(tmp_path):
    cmd, note = _page(tmp_path, "http://10.0.0.9:8787", "https://ledger.example.com")
    assert cmd == "curl -fsSL http://10.0.0.9:8787/install.sh | sh -s -- --pair CODE_abcdefghij" and "example.com" not in cmd
    assert "http://10.0.0.9:8787" in note


def test_settings_page_shows_a_message_not_a_command_when_no_lan_address_is_known(tmp_path):
    cmd, note = _page(tmp_path, None, "https://ledger.example.com")
    assert not cmd.startswith("curl") and "BLOOM_LEDGER_LAN_URL" in cmd and "example.com" not in cmd.replace("BLOOM_LEDGER_LAN_URL", "")
    assert "local network address" in note
