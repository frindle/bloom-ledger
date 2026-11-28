"""scripts/connect-app.sh and bloom_keys.py: the env file is rewritten in place and the key is never printed. Fake docker, fake data."""
import os
import stat
import subprocess
from pathlib import Path

import bloom_api_keys as AK
import bloom_ingest as I
import bloom_keys as BK

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "connect-app.sh"
KEY = "blk_" + "x" * 43


def fake_docker(tmp_path, output=KEY + "\n"):
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    (d / "docker").write_text("#!/bin/sh\necho \"$@\" > \"%s\"\nprintf '%%s' '%s'\n" % (tmp_path / "args", output.replace("\n", "")))
    (d / "docker").chmod(0o755)
    return d


def run(tmp_path, env_file, *extra, output=KEY):
    env = dict(os.environ, PATH=str(fake_docker(tmp_path, output)) + os.pathsep + os.environ["PATH"])
    return subprocess.run(["bash", str(SCRIPT), "tracker", str(env_file), *extra], capture_output=True, text=True, env=env)


def test_replaces_the_variable_and_keeps_other_lines_and_mode(tmp_path):
    f = tmp_path / "app.env"
    f.write_text("A=1\nBLOOM_LEDGER_TOKEN=old\nB=2 # keep\n")
    f.chmod(0o640)
    ino = f.stat().st_ino
    r = run(tmp_path, f)
    assert r.returncode == 0, r.stderr
    assert f.read_text() == "A=1\nBLOOM_LEDGER_TOKEN=%s\nB=2 # keep\n" % KEY
    assert stat.S_IMODE(f.stat().st_mode) == 0o640 and f.stat().st_ino == ino
    assert r.stdout.strip() == "key 'tracker' written to %s as BLOOM_LEDGER_TOKEN" % f
    assert KEY not in r.stdout and KEY not in r.stderr
    (bak,) = [p for p in tmp_path.iterdir() if ".bak-" in p.name]
    assert bak.read_text() == "A=1\nBLOOM_LEDGER_TOKEN=old\nB=2 # keep\n" and stat.S_IMODE(bak.stat().st_mode) == 0o600
    assert "compose exec -T bloom-ledger python3 /app/bloom_keys.py create --label tracker --replace" in (tmp_path / "args").read_text()


def test_appends_when_missing_even_without_a_trailing_newline(tmp_path):
    f = tmp_path / "app.env"
    f.write_text("A=1\nOTHER_TOKEN=keep")
    r = run(tmp_path, f, "MY_KEY")
    assert r.returncode == 0, r.stderr
    assert f.read_text() == "A=1\nOTHER_TOKEN=keep\nMY_KEY=%s\n" % KEY


def test_a_longer_name_with_the_same_start_is_not_replaced(tmp_path):
    f = tmp_path / "app.env"
    f.write_text("BLOOM_LEDGER_TOKEN_OLD=1\n")
    run(tmp_path, f)
    assert f.read_text() == "BLOOM_LEDGER_TOKEN_OLD=1\nBLOOM_LEDGER_TOKEN=%s\n" % KEY


def test_refuses_a_missing_file_and_a_bad_reply_and_leaves_the_file(tmp_path):
    r = run(tmp_path, tmp_path / "nope.env")
    assert r.returncode == 1 and "not found" in r.stderr
    f = tmp_path / "app.env"
    f.write_text("A=1\n")
    r = run(tmp_path, f, output="Error: no such service")
    assert r.returncode == 1 and f.read_text() == "A=1\n"


def test_cli_create_replace_list_revoke(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BLOOM_DATA", str(tmp_path))
    import io
    out = io.StringIO()
    assert BK.main(["create", "--label", "t"], out=out) == 0
    k1 = out.getvalue().strip()
    out = io.StringIO()
    assert BK.main(["create", "--label", "t", "--replace"], out=out) == 0
    k2 = out.getvalue().strip()
    db = I.open_db(tmp_path / "index.sqlite")
    assert k1.startswith("blk_") and k2.startswith("blk_") and k1 != k2
    assert AK.verify(db, k1) is None and AK.verify(db, k2) is not None
    out = io.StringIO()
    BK.main(["list"], out=out)
    assert out.getvalue().startswith("t\tcreated ") and k2 not in out.getvalue()
    assert BK.main(["revoke", "--label", "t"], err=io.StringIO()) == 0
    assert AK.verify(db, k2) is None
    assert BK.main(["revoke", "--label", "t"], err=io.StringIO()) == 1
    assert BK.main(["create", "--label", " "], out=io.StringIO(), err=io.StringIO()) == 1
