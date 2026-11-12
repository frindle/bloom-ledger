import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ.setdefault("BLOOM_POWER_HOME", _tmp)
_spec = importlib.util.spec_from_file_location("earnings_archive", Path(__file__).resolve().parent / "bloom-earnings-archive.py")
EA = importlib.util.module_from_spec(_spec)
sys.path.insert(0, str(Path(__file__).resolve().parent))
_spec.loader.exec_module(EA)


class _R:
    def __init__(self, rc):
        self.returncode = rc


def test_runs_archive_with_state_dir(tmp_path):
    (tmp_path / "bloom-archive.py").write_text("")
    calls = []
    ok = EA.archive_now("/state/x", script_dir=tmp_path, run=lambda cmd, **kw: calls.append((cmd, kw)) or _R(0))
    assert ok is True
    cmd, kw = calls[0]
    assert cmd == [sys.executable, str(tmp_path / "bloom-archive.py")]
    assert kw["env"]["BLOOM_POWER_HOME"] == "/state/x" and kw["timeout"] == 120


def test_missing_script_is_skipped(tmp_path):
    assert EA.archive_now("/s", script_dir=tmp_path, run=lambda *a, **k: (_ for _ in ()).throw(AssertionError)) is False


def test_failures_return_false(tmp_path):
    (tmp_path / "bloom-archive.py").write_text("")
    assert EA.archive_now("/s", script_dir=tmp_path, run=lambda *a, **k: _R(1)) is False

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("x", 120)
    assert EA.archive_now("/s", script_dir=tmp_path, run=boom) is False


def test_install_polls_earnings_every_5_min():
    assert "plist earnings 300 bloom-earnings-archive.py" in (Path(__file__).resolve().parent.parent / "client" / "install.sh").read_text()
