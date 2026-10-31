"""Frozen test: bloom-manifest.py writes hash-chained manifests only; no OpenTimestamps stamping or `upgrade`."""
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "bloom-manifest.py"
BANNED = re.compile(r"opentimestamps|bitcoin|\bots\b|ots_|_ots|\.ots\b|shutil|stamp", re.I)


def run(home, *args):
    env = dict(os.environ, BLOOM_POWER_HOME=str(home), BLOOM_MACHINE_ID="m4max", PATH="/usr/bin:/bin")
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, cwd=str(home), capture_output=True,
                          text=True, timeout=60)


def test_daily_writes_only_manifest_files_and_no_ots_warning(tmp_path):
    first = run(tmp_path, "daily", "--day", "2026-10-29")
    assert first.returncode == 0, first.stderr
    assert first.stdout.split() == ["2026-10-29", "written"], first.stdout
    assert "ots" not in first.stderr.lower(), first.stderr
    names = sorted(p.name for p in (tmp_path / "ledger").iterdir())
    assert names == ["manifest-2026-10-29.json"], names
    again = run(tmp_path, "daily", "--day", "2026-10-29")
    assert again.stdout.split() == ["2026-10-29", "same"], again.stdout
    verify = run(tmp_path, "verify")
    assert verify.returncode == 0 and "VERIFY OK" in verify.stdout, verify.stdout


def test_upgrade_subcommand_is_gone(tmp_path):
    res = run(tmp_path, "upgrade")
    assert res.returncode == 2, (res.returncode, res.stdout, res.stderr)
    assert "invalid choice" in res.stderr


def test_script_text_mentions_no_ots_or_bitcoin():
    hit = BANNED.search(SCRIPT.read_text())
    assert hit is None, hit and hit.group(0)
