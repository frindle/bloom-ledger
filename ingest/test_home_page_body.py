"""Frozen test: the home page markup (labels, tables, nav, element ids)."""
import re

import bloom_accounting_page as PG


def test_controls_and_navigation():
    h = PG.body_html()
    assert h.strip().startswith("<main>") and h.strip().endswith("</main>")
    assert '<a href="/log">Log</a>' in h and '<a href="/settings">Settings</a>' in h and "<h1>Ledger</h1>" in h
    assert 'for="period"' in h and 'id="period"' in h and 'for="machine"' in h and 'id="machine"' in h
    assert [v for v in re.findall(r'<option value="([^"]*)"', h)][:7] == ["day", "week", "month", "quarter", "ytd", "last_year", ""]
    assert 'value="month" selected' in h and "All machines" in h
    assert 'id="banner"' in h and "hidden" in h and 'role="alert"' in h and 'id="alerts"' in h


def test_tables_are_accessible():
    h = PG.body_html()
    assert h.count("<caption>") == 2 and 'id="day-rows"' in h and 'id="entry-rows"' in h
    assert h.count('scope="col"') == 13
    for label in ("Earned", "Energy (kWh)", "Hours", "Tokens", "Category", "Amount", "Status"):
        assert ">" + label + "<" in h, label
    assert 'id="summary"' in h and 'id="power-note"' in h
    assert not re.search(r"https?://|onclick=|<script", h)
