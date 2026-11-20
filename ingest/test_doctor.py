"""Server and client doctor, plus the Mac scripts' syntax. Fake data."""
import json
import subprocess
import sys
from pathlib import Path

import bloom_doctor as DOC

CLIENT = Path(__file__).resolve().parent.parent / "client"
sys.path.insert(0, str(CLIENT))
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("client_doctor", CLIENT / "bloom-doctor.py")
CD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CD)


def names(rows, status):
    return {r[1] for r in rows if r[0] == status}


def test_server_doctor_on_an_empty_install_has_no_failures(tmp_path):
    rows = DOC.checks(tmp_path, tmp_path / "t", tmp_path / "m.json", 1, 0)
    assert not names(rows, "FAIL") - {"Server answers on port 1"}
    assert ("INFO", "BloomGauge (optional)", "optional: not set up", "Nothing to do. It is never required.") in rows


def test_server_doctor_flags_an_unwritable_folder(tmp_path):
    f = tmp_path / "file"
    f.write_text("x")
    rows = DOC.checks(f / "sub", tmp_path / "t", tmp_path / "m.json", 1, 0)
    assert "Data folder is writable" in names(rows, "FAIL")
    assert all(r[3] for r in rows if r[0] == "FAIL")          # every failure says how to fix it


def test_client_doctor_unpaired_says_what_to_do(tmp_path):
    rows = CD.checks(tmp_path, env={}, fetch=lambda *a, **k: (None, b""), keychain=lambda m: "", loaded=lambda l: False)
    assert rows[0][0] == "FAIL" and "install" in rows[0][3]


def paired(tmp_path, **cfg):
    (tmp_path / "ledger.json").write_text(json.dumps(dict(machine_id="m1", ingest_url="http://192.168.1.20:8787", **cfg)))
    (tmp_path / "wallet.log").write_text("x")


def test_client_doctor_all_good_and_bloomgauge_optional(tmp_path):
    paired(tmp_path)
    rows = CD.checks(tmp_path, env={}, fetch=lambda *a, **k: (200, b""), keychain=lambda m: "tok", loaded=lambda l: True, which=lambda n: "/x/macmon")
    assert not names(rows, "FAIL") and not names(rows, "WARN")
    assert [r for r in rows if r[1].startswith("BloomGauge")][0][2] == "optional: not set up"
    paired(tmp_path, bloomgauge=True)
    rows = CD.checks(tmp_path, env={}, fetch=lambda *a, **k: (200, b""), keychain=lambda m: "tok", loaded=lambda l: True, which=lambda n: "x")
    assert [r for r in rows if r[1].startswith("BloomGauge")][0][2] == "switched on"


def test_client_doctor_reports_each_failure_with_a_fix(tmp_path):
    paired(tmp_path)
    rows = CD.checks(tmp_path, env={}, fetch=lambda u, t=None, timeout=6: (None, b"") if "hello" in u else (401, b""),
                     keychain=lambda m: "", loaded=lambda l: False, which=lambda n: None)
    bad = names(rows, "FAIL")
    assert {"Ledger is reachable", "Token is in the Keychain", "Background jobs loaded"} <= bad
    assert all(r[3] for r in rows if r[0] == "FAIL")
    rows = CD.checks(tmp_path, env={}, fetch=lambda u, t=None, timeout=6: (200, b"") if "hello" in u else (401, b""),
                     keychain=lambda m: "tok", loaded=lambda l: True)
    assert "Ledger accepts this Mac's token" in names(rows, "FAIL")


def test_mac_scripts_parse():
    root = CLIENT.parent / "deploy" / "mac"
    for s in (root / "install-server.sh", root / "uninstall-server.sh", CLIENT / "install.sh"):
        assert subprocess.run(["sh", "-n", str(s)]).returncode == 0, s
