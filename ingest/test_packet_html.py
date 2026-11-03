"""Frozen test: bloom_accounting_packet renders the year-end packet as printable, escaped HTML. Fake data."""
import bloom_accounting_packet as PK


def mod():
    assert hasattr(PK, "money") and hasattr(PK, "packet_html"), "money / packet_html missing"
    return PK


def data():
    lines = [{"line": n, "label": lbl, "micro": m} for n, lbl, m in (
        ("1", "Gross receipts (Darkbloom pay)", 1234567890), ("6", "Other income", 0), ("13", "Depreciation (Form 4562)", 52280000),
        ("18", "Office expense (software)", 12000000), ("20a", "Rent or lease of equipment", None), ("22", "Supplies", 0),
        ("25", "Utilities (metered electricity, internet)", 26750000), ("27a", "Other expenses", 15000000))]
    return {"year": 2026, "prepared": "2027-01-15", "lines": lines, "expenses_micro": None, "net_micro": -383000,
            "entries": [{"id": 2, "date": "2026-04-01", "kind": "cost", "category": "software", "vendor": "Tools & <Co>",
                         "purpose": "<script>alert(1)</script>", "business_pct": 50, "amount_cents": 2400, "line": "18",
                         "deduct_micro": 12000000, "receipt": None, "needs": ["receipt"]},
                        {"id": 1, "date": "2026-09-01", "kind": "cost", "category": "hardware", "vendor": "Apple", "purpose": "Mac",
                         "business_pct": 100, "amount_cents": 182600, "line": "13", "deduct_micro": None,
                         "receipt": "entry-1-ab.pdf", "needs": []}],
            "assets": [{"id": 1, "date": "2026-09-01", "vendor": "Apple", "purpose": "Mac", "basis_cents": 182600,
                        "placed_in_service": "2026-09-28", "method": "macrs5", "year_cents": 36520}],
            "use": {"business_bp": 8754, "minutes": 51234, "kwh": 101.5},
            "flags": [{"key": "dep_method", "reason": "DEFAULT macrs5 & confirm"}], "disclaimer": "Bookkeeping, not tax advice."}


def test_cents_money():
    P = mod()
    assert P.cents_money(None) == "not set" and P.cents_money(182600) == "$1,826.00" and P.cents_money(-5) == "-$0.05"


def test_money():
    P = mod()
    assert P.money(None) == "not set" and P.money(0) == "$0.00" and P.money(123456789) == "$123.45"
    assert P.money(100000000000) == "$100,000.00" and P.money(-10000) == "-$0.01" and P.money(-383000) == "-$0.38"
    assert P.money(9999) == "$0.00", "rounds down to the cent"


def test_packet_html():
    P = mod()
    h = P.packet_html(data())
    assert h.startswith("<!doctype html>") and "<title>Tax packet 2026</title>" in h
    heads = ["Schedule C summary", "Business use of the machine", "Depreciation schedule", "Income and expense entries",
             "To confirm with your preparer"]
    pos = [h.find("<h2>%s</h2>" % s) for s in heads]
    assert all(p > 0 for p in pos) and pos == sorted(pos), pos
    assert "<script>" not in h and "&lt;script&gt;alert(1)&lt;/script&gt;" in h and "Tools &amp; &lt;Co&gt;" in h
    assert "$1,234.56" in h and "$52.28" in h and "-$0.38" in h
    assert h.count("not set") >= 2, "a None line and None total expenses show not set"
    assert "87.54%" in h and "51,234" in h and "101.5" in h
    assert "5-year MACRS, half-year" in h and "$1,826.00" in h and "$365.20" in h and "2026-09-28" in h
    assert "depreciated" in h and "entry-1-ab.pdf" in h and "missing" in h
    assert "DEFAULT macrs5 &amp; confirm" in h and "Entry 2 (2026-04-01): add receipt" in h
    assert "Bookkeeping, not tax advice." in h and "Prepared 2027-01-15" in h and "@media print" in h
    empty = dict(data(), entries=[], assets=[], flags=[])
    e = P.packet_html(empty)
    assert "No entries" in e and "No hardware entries" in e and "Nothing to confirm." in e
