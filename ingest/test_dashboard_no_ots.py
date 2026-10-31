"""Frozen test: dashboard.html shows days as sealed / open / missing only (log view since the redesign); no Bitcoin or OpenTimestamps wording."""
import re
from pathlib import Path

HTML = Path(__file__).resolve().parent / "dashboard.html"
BANNED = re.compile(r"bitcoin|opentimestamps|\bots\b|ots-not-upgraded|(?<!-)waiting|pending|timestamp", re.I)


def test_page_has_no_bitcoin_or_timestamp_wording():
    hits = sorted({m.group(0).lower() for m in BANNED.finditer(HTML.read_text())})
    assert hits == [], hits


def test_banner_counts_only_sealed_and_missing_days():
    src = HTML.read_text()
    assert "const pending" not in src
    status = re.search(r'getElementById\("status"\)\.textContent = (.*?);\n', src, re.S).group(1)
    assert "days sealed" in status and "missing a manifest" in status and "still" not in status
    assert 'if (a.alert === "machine-silent")' in src and 'if (a.alert === "ring-snapshot-stale")' in src
