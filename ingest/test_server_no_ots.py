"""Frozen test: server.py no longer stamps or upgrades OpenTimestamps proofs."""
import os
import re
import subprocess
import sys

import server

OTS_WORDS = re.compile(r"opentimestamps|bitcoin|\bots\b|ots[-_]|[-_]ots|ots upgrade", re.I)


def test_scheduler_writes_manifests_and_no_ots_files(tmp_path):
    code = (
        "import sys, threading, time\n"
        "from pathlib import Path\n"
        "import bloom_ingest as I\n"
        "import server\n"
        "root = Path(sys.argv[1])\n"
        "db = I.open_db(root / 'index.sqlite')\n"
        "I.index_object(db, 'm4max', 'log', 'a' * 64, 1, time.time() - 3 * 86400)\n"
        "stop = threading.Event()\n"
        "threading.Thread(target=server.scheduler, args=(db, stop), daemon=True).start()\n"
        "ledger = root / 'ledger' / 'm4max'\n"
        "for _ in range(80):\n"
        "    time.sleep(0.1)\n"
        "    if len(list(ledger.glob('manifest-*.json'))) >= 3:\n"
        "        break\n"
        "time.sleep(0.5)\n"
        "stop.set()\n"
    )
    env = dict(os.environ, BLOOM_DATA=str(tmp_path), BLOOM_TOKENS=str(tmp_path / "none"),
               PYTHONPATH=os.pathsep.join(sys.path))
    subprocess.run([sys.executable, "-c", code, str(tmp_path)], env=env, cwd=str(tmp_path), timeout=60,
                   capture_output=True)
    ledger = tmp_path / "ledger" / "m4max"
    names = sorted(p.name for p in ledger.iterdir()) if ledger.is_dir() else []
    assert len(names) >= 3, names
    assert all(re.fullmatch(r"manifest-\d{4}-\d{2}-\d{2}\.json", n) for n in names), names


def test_server_has_no_ots_binary_or_upgrade_code():
    assert not hasattr(server, "OTS_BIN")
    src = open(server.__file__).read()
    hit = OTS_WORDS.search(src)
    assert hit is None, hit and hit.group(0)
    assert "import shutil" not in src and "last_upgrade" not in src


def test_docstring_lists_only_the_two_remaining_alerts():
    doc = server.__doc__
    assert "machine silent > 30 min, ring snapshot > 12 h" in doc
    assert "OTS" not in doc and "OpenTimestamps" not in doc and "ots upgrade" not in doc
