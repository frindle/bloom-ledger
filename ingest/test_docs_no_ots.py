"""Frozen test: Dockerfile, README and compose.yaml carry no OpenTimestamps / Bitcoin wording or dependency."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANNED = re.compile(r"opentimestamps|bitcoin|\bots\b|\.ots\b|un-upgraded|pip install --no-cache-dir", re.I)


def test_dockerfile_installs_nothing_and_keeps_the_bloom_user():
    src = (ROOT / "Dockerfile").read_text()
    assert BANNED.search(src) is None, BANNED.search(src).group(0)
    assert "pip install" not in src
    assert "RUN useradd --uid 99 --gid 100 --no-create-home --home-dir /state bloom 2>/dev/null || true" in src
    assert "FROM python:3.12-slim" in src and 'CMD ["python3", "/app/server.py"]' in src
    assert "COPY ingest/server.py" in src and "USER 99:100" in src


def test_readme_describes_hash_chained_manifests_without_ots():
    src = (ROOT / "README.md").read_text()
    assert BANNED.search(src) is None, BANNED.search(src).group(0)
    assert "closes each UTC day into a hash-chained manifest." in src
    assert "`/v1/alerts` reports silent machines and stale ring snapshots." in src
    assert "## Settings page" in src and "## Tests" in src


def test_compose_comment_mentions_manifests_only():
    src = (ROOT / "compose.yaml").read_text()
    assert BANNED.search(src) is None, BANNED.search(src).group(0)
    assert "(objects, ledger manifests, index.sqlite)" in src
