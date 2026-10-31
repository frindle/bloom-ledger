"""Frozen test: ingest/settings.html (static shell)."""
import re
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKENS = ["paper", "card", "ink", "muted", "rule", "sealed", "waiting", "missing", "serif", "mono"]


class Page(HTMLParser):
    """Collects start tags (tag, attrs) and per-tag text so tests can ask structural questions."""

    def __init__(self, html):
        super().__init__()
        self.tags, self.stack, self.text = [], [], {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag not in ("meta", "link", "input", "br", "hr"):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass

    def handle_data(self, data):
        if self.stack and data.strip():
            self.text.setdefault(self.stack[-1], []).append(data.strip())

    def find(self, tag, **attrs):
        return [a for t, a in self.tags if t == tag and all(a.get(k) == v for k, v in attrs.items())]


def settings_html():
    return (HERE / "settings.html").read_text()


def token_values(css_text):
    return {n: v.strip() for n, v in re.findall(r"--(\w+):\s*([^;]+);", css_text)}


def test_page_basics():
    html = settings_html()
    page = Page(html)
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert page.find("html", lang="en") and page.find("meta", name="viewport")
    assert "Settings" in page.text.get("h1", []) and any("Settings" in t for t in page.text.get("title", []))
    assert page.find("a", href="/"), "a link back to the ledger"
    assert page.find("p", id="admin-note"), "the admin explanation lives here"


def test_reuses_the_dashboard_css_tokens():
    mine = token_values(settings_html())
    theirs = token_values((HERE / "dashboard.html").read_text())
    for name in TOKENS:
        assert name in mine and mine[name] == theirs[name], f"--{name}: {mine.get(name)!r} vs {theirs[name]!r}"
    assert ":focus-visible" in settings_html()


def test_machines_table_has_the_agreed_columns():
    page = Page(settings_html())
    assert page.find("table", id="machines") and page.find("tbody", id="machine-rows")
    heads = [t for t, a in page.tags if t == "th"]
    assert len(heads) == 6 and all(a.get("scope") == "col" for t, a in page.tags if t == "th")
    assert page.text["th"] == ["Machine", "Last seen", "Objects", "Days sealed", "Status", "Actions"]
    assert page.find("caption"), "the table needs a caption for screen readers"
