"""Frozen test: the ledger home page has an inline, accessible, mobile-friendly stylesheet with no external assets."""
import re

import bloom_accounting_page as PG


def test_stylesheet_rules():
    css = PG.style_block()
    assert css.strip().startswith("<style>") and css.strip().endswith("</style>")
    for token in ("--paper", "--ink", "--bad", ".banner[hidden]", "dl.figures", "tr.voided", ".notset", ":focus-visible",
                  "@media (max-width: 40rem)", "prefers-reduced-motion"):
        assert token in css, token
    assert "td.num" in css and ".picker" in css and ".top" in css


def test_no_external_assets():
    css = PG.style_block()
    assert "<style>" in css and not re.search(r"https?://|@import|url\(", css, re.I)
