"""Frozen test: bloom_accounting_settings_form.settings_form_page (the /settings/accounting HTML)."""
from html.parser import HTMLParser

import bloom_accounting_settings_form as F


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def find(self, tag, **attrs):
        return [a for t, a in self.tags if t == tag and all(a.get(k) == v for k, v in attrs.items())]


def test_form_controls_flag_and_title():
    html = F.settings_form_page()
    page = Page(html)
    assert html.startswith("<!doctype html>") and "<title>Accounting settings</title>" in html and "<h1>Accounting settings</h1>" in html
    assert page.find("form", id="acct-form") and page.find("label", **{"for": "effective-from"}) and page.find("input", id="effective-from", required=None)
    assert page.find("span", id="status") and page.find("button", type="submit")
    assert "<strong>Bookkeeping, not tax advice.</strong>" in html and "Confirm with CPA: depreciation method, elections and business-use figures." in html
    assert F.settings_form_rows() in html and html.index("effective-from") < html.index(F.settings_form_rows()) < html.index('id="status"')


def test_inline_script_and_no_external_resources():
    html = F.settings_form_page()
    assert "<script>" + F.settings_form_script() + F.settings_form_wiring() + "</script>" in html
    assert "http://" not in html and "https://" not in html and "src=" not in html and "<style>" in html
    assert "left unchanged" in html and "new dated row" in html
