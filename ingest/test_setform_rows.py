"""Frozen test: bloom_accounting_settings_form.settings_form_rows (the setting fields of the accounting form)."""
from html.parser import HTMLParser

import bloom_accounting_settings_form as F


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def find(self, tag, **attrs):
        return [a for t, a in self.tags if t == tag and all(a.get(k) == v for k, v in attrs.items())]

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


KEYS = {"dep_method": "text", "dep_life_months": "int", "m4_in_service_date": "text", "rate_schedule": "json", "rate_adder_usd_per_kwh": "text",
        "universal_charge_usd_per_kwh": "text", "county_fee_pct": "text", "m5_lease_monthly_cents": "int", "m5_lease_months": "int",
        "m5_lease_start": "text", "machines": "json"}


def test_every_setting_has_a_labelled_typed_control_in_order():
    html = F.settings_form_rows()
    page = Page(html)
    ctl = [a for t, a in page.tags if t in ("input", "select", "textarea") and "data-key" in a]
    assert [a["data-key"] for a in ctl] == list(KEYS) and {a["data-key"]: a["data-type"] for a in ctl} == KEYS
    for key in KEYS:
        assert page.find("label", **{"for": "f-" + key}), key
        assert any(a.get("id") == "f-" + key for a in ctl), key
    assert html.count("<p>") == 11 and html.count("</p>") == 11 and "<form" not in html


def test_control_kinds_and_depreciation_options():
    page = Page(F.settings_form_rows())
    assert [t for t, a in page.tags if t == "textarea"] == ["textarea", "textarea"] and len(page.find("select")) == 1
    assert len([1 for t, a in page.tags if t == "input"]) == 8
    assert [a["value"] for t, a in page.tags if t == "option"] == ["", "macrs5", "straight_line", "section179"]
