"""Sandbox status.json resolution (env, LaunchAgent --config dir, ~/DarkbloomSandbox, legacy) and the loud missing/stale case."""
import importlib.util
import os
import plistlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bloom_power_lib as L

NOW = 1793680600.0


def mk(p, age=10, jobs=2):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"jobs_running": %d}' % jobs)
    os.utime(p, (NOW - age, NOW - age))
    return p


def plist(tmp, cfg):
    f = tmp / "sb.plist"
    f.write_bytes(plistlib.dumps({"ProgramArguments": ["/x/agent", "--config", str(cfg)],
                                  "EnvironmentVariables": {"SECRET": "no"}}))
    return str(f)


def home(tmp, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp / "h"))


def test_env_wins(tmp_path, monkeypatch):
    home(tmp_path, monkeypatch)
    e = mk(tmp_path / "env" / "s.json")
    mk(tmp_path / "h/DarkbloomSandbox/agent/status.json")
    p, _ = L.resolve_sandbox_status({"BLOOM_SANDBOX_STATUS": str(e)}, plist(tmp_path, tmp_path / "c" / "agent.json"))
    assert p == e


def test_plist_config_dir(tmp_path, monkeypatch):
    home(tmp_path, monkeypatch)
    s = mk(tmp_path / "c" / "status.json")
    mk(tmp_path / "h/DarkbloomSandbox/agent/status.json")
    p, _ = L.resolve_sandbox_status({}, plist(tmp_path, tmp_path / "c" / "agent.json"))
    assert p == s


def test_plist_sh_wrapper_positional_config(tmp_path, monkeypatch):
    # the real Sandbox installer plist: --config sits inside the sh -c script, the path is a positional argument
    home(tmp_path, monkeypatch)
    s = mk(tmp_path / "moved" / "agent" / "status.json")
    mk(tmp_path / "h/DarkbloomSandbox/agent/status.json")
    f = tmp_path / "real.plist"
    script = ('exe=$0 app=$1 log=$2 config=$3; while pgrep -q -f "^$exe agent "; do sleep 5; done; '
              'exec open -n -g -W --stdout "$log" --stderr "$log" "$app" --args agent --config "$config"')
    f.write_bytes(plistlib.dumps({"ProgramArguments": [
        "/bin/sh", "-c", script, "/x/DarkbloomSandbox.app/Contents/MacOS/darkbloom-sandbox", "/x/DarkbloomSandbox.app",
        str(tmp_path / "moved/agent/agent.log"), str(tmp_path / "moved/agent/agent.json")]}))
    assert L.sandbox_plist_status(str(f)) == s
    p, _ = L.resolve_sandbox_status({}, str(f))
    assert p == s


def test_plist_without_config_falls_through(tmp_path, monkeypatch):
    home(tmp_path, monkeypatch)
    s = mk(tmp_path / "h/DarkbloomSandbox/agent/status.json")
    f = tmp_path / "noconf.plist"
    f.write_bytes(plistlib.dumps({"ProgramArguments": ["/bin/sh", "-c", "exec agent", "/x/agent.log"]}))
    assert L.sandbox_plist_status(str(f)) is None
    p, _ = L.resolve_sandbox_status({}, str(f))
    assert p == s


def test_home_default(tmp_path, monkeypatch):
    home(tmp_path, monkeypatch)
    s = mk(tmp_path / "h/DarkbloomSandbox/agent/status.json")
    p, _ = L.resolve_sandbox_status({}, str(tmp_path / "none.plist"))
    assert p == s


def test_legacy_last(tmp_path, monkeypatch):
    home(tmp_path, monkeypatch)
    assert L.sandbox_status_candidates({}, str(tmp_path / "none.plist"))[-1] == Path(L.SANDBOX_LEGACY_STATUS)


def test_missing_with_plist_is_loud(tmp_path, monkeypatch):
    home(tmp_path, monkeypatch)
    pl = plist(tmp_path, tmp_path / "c" / "agent.json")
    jobs, note = L.read_sandbox_auto(NOW, {}, pl)
    assert jobs == 0 and note.startswith(L.SANDBOX_PROBLEM_NOTE) and str(tmp_path / "c" / "status.json") in note
    assert "SECRET" not in note


def test_missing_without_plist_is_quiet(tmp_path, monkeypatch):
    home(tmp_path, monkeypatch)
    assert L.read_sandbox_auto(NOW, {}, str(tmp_path / "none.plist")) == (0, "")


def test_stale_is_loud_fresh_is_not(tmp_path, monkeypatch):
    home(tmp_path, monkeypatch)
    pl = plist(tmp_path, tmp_path / "c" / "agent.json")
    s = mk(tmp_path / "c" / "status.json", age=1000)
    assert L.read_sandbox_auto(NOW, {}, pl)[1].startswith(L.SANDBOX_PROBLEM_NOTE)
    mk(s, age=10)
    assert L.read_sandbox_auto(NOW, {}, pl) == (2, "")


def test_bounded_read_incident_once(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("bpl", HERE.parent / "client" / "bloom-power-log.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    seen = []
    note = L.SANDBOX_PROBLEM_NOTE + ": x"
    r = m.BoundedSandboxRead(None, read=lambda now: (0, note), incident=lambda k, **f: seen.append(k))
    r(NOW), r(NOW)
    assert seen == ["status-problem"] and "WARNING" in capsys.readouterr().err
