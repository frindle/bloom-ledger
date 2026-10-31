"""Frozen test: ingest/settings.html (add form, health and machine-names sections)."""
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent


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


def test_add_form_and_health_sections():
    page = Page(settings_html())
    assert page.find("form", id="add-form") and page.find("dl", id="health") and any(t == "div" and a.get("id") == "onboarding" and "hidden" in a for t, a in page.tags), "add form, health list and hidden onboarding block"
    inputs = page.find("input", id="new-id")
    assert inputs and inputs[0].get("autocomplete") == "off"
    assert page.find("label", **{"for": "new-id"}), "the id input has a label"
    assert page.find("button", type="submit")
    for heading in ("Machines", "Add a machine", "Ledger health", "Machine names"):
        assert heading in page.text.get("h2", []), heading


def test_rename_is_text_not_a_button():
    html = settings_html()
    page = Page(html)
    assert "cannot be renamed" in html and "write-once" in html and "hash-chained" in html, "machine names text"
    assert not any("rename" in " ".join(str(v) for v in a.values()).lower() for t, a in page.tags if t in ("button", "input", "a"))
    assert not any("rename" in t.lower() for t in page.text.get("button", []))
