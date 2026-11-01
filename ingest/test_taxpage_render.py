"""Frozen test: bloom_accounting_taxpage.tax_page (the /tax page HTML). Fake data only."""
from html.parser import HTMLParser

import pytest

import bloom_accounting_taxpage as P


class Page(HTMLParser):
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


def test_controls_table_and_label():
    html = P.tax_page(2031)
    page = Page(html)
    assert "Bookkeeping, not tax advice" in html and page.find("p", id="disclaimer")
    opts = [a for t, a in page.tags if t == "option"]
    assert ["2031"] == [a["value"] for a in opts if "selected" in a and a["value"].isdigit()]
    assert {"2026", "2032"} <= {a["value"] for a in opts}
    assert page.find("select", id="year") and page.find("select", id="view") and page.find("a", id="csv") and page.find("a", id="json")
    assert page.find("button", id="print") and page.find("table", id="months") and page.find("tbody", id="rows")
    assert {"business", "hobby"} <= {a["value"] for a in opts}


def test_print_stylesheet_script_and_no_external_resources():
    html = P.tax_page(2031)
    assert "@media print" in html and "noprint" in html and P.tax_page_script() in html
    assert "<title>Tax year 2031</title>" in html
    assert "http://" not in html and "https://" not in html and "src=" not in html
    for bad in ("2031", "x", None, True, 2031.0):
        with pytest.raises(ValueError):
            P.tax_page(bad)
