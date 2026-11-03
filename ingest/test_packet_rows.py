"""Frozen test: bloom_accounting_packet turns ledger entries into packet rows and suggested Schedule C lines. Fake data."""
import bloom_accounting_packet as PK


def row(**kw):
    e = {"id": 1, "date": "2025-10-05", "kind": "cost", "amount_cents": 8000, "category": "internet", "vendor": "ISP",
         "purpose": "Home internet", "receipt": "entry-1-ab.pdf"}
    e.update(kw)
    return e


def test_entry_row():
    r = PK.entry_row(row(), 3333)
    assert r["line"] == "25" and r["deduct_micro"] == 8000 * 3333 // 10000 * 10000 and r["needs"] == [] and r["business_pct"] == 100
    assert r["vendor"] == "ISP" and r["purpose"] == "Home internet" and r["receipt"] == "entry-1-ab.pdf" and r["amount_cents"] == 8000
    assert PK.entry_row(row(category="electricity"), 3333)["deduct_micro"] == 0, "metered power already counts the bill"
    hw = PK.entry_row(row(category="hardware", receipt=None), 3333)
    assert hw["line"] == "13" and hw["deduct_micro"] is None and hw["needs"] == ["receipt"]
    sw = PK.entry_row(row(category="software", amount_cents=2400, business_pct=50), None)
    assert sw["line"] == "18" and sw["business_pct"] == 50 and sw["deduct_micro"] == 12000000
    rc = PK.entry_row(row(kind="receipt", category="other", amount_cents=3000), None)
    assert rc["line"] == "6" and rc["deduct_micro"] == 30000000 and rc["kind"] == "receipt"
    bare = PK.entry_row({"id": 9, "kind": "cost", "date": "2025-05-01", "amount_cents": 100, "category": "supplies"}, None)
    assert bare["line"] == "22" and bare["needs"] == ["vendor", "purpose", "receipt"] and bare["vendor"] is None
    assert PK.entry_row(row(category="other", vendor=""), 0)["line"] == "27a"
    assert PK.entry_row(row(category="other", vendor=""), 0)["needs"] == ["vendor"]


def test_packet_lines():
    def r(i, kind, cat, line, deduct):
        return {"id": i, "kind": kind, "category": cat, "line": line, "deduct_micro": deduct}
    rows = [r(1, "cost", "software", "18", 1000000), r(2, "cost", "software", "18", 2000000), r(3, "cost", "supplies", "22", 500000),
            r(4, "cost", "internet", "25", 10000000), r(5, "cost", "electricity", "25", 4000000), r(6, "cost", "other", "27a", 700000),
            r(7, "cost", "hardware", "13", None), r(8, "receipt", "other", "6", 50000000), r(9, "receipt", "other", "27a", 9),
            r(10, "cost", "interest", "16b", 2500000)]
    t = {"income_micro": 7, "other_income_micro": 50000000, "depreciation_business_micro": 11, "lease_business_micro": 13,
         "power_business_micro": 1000000}
    out = PK.packet_lines(t, rows)
    assert [l["line"] for l in out] == ["1", "6", "13", "16b", "18", "20a", "22", "25", "27a"]
    assert out[0]["label"] == "Gross receipts (Darkbloom pay)" and out[8]["label"] == "Other expenses" and out[3]["label"] == "Interest (machine loan)"
    v = {l["line"]: l["micro"] for l in out}
    assert v == {"1": 7, "6": 50000000, "13": 11, "16b": 2500000, "18": 3000000, "20a": 13, "22": 500000, "25": 11000000, "27a": 700000}, v
    nv = {l["line"]: l["micro"] for l in PK.packet_lines(dict(t, power_business_micro=None, lease_business_micro=None), rows)}
    assert nv["25"] is None and nv["20a"] is None and nv["18"] == 3000000


def test_interest_entry_counts_at_the_business_share():
    e = {"id": 3, "date": "2026-10-01", "kind": "cost", "category": "interest", "amount_cents": 10000, "business_pct": 100,
         "vendor": "Credit union", "purpose": "Machine loan interest", "receipt": "x.pdf"}
    r = PK.entry_row(e, 2500)
    assert r["line"] == "16b" and r["deduct_micro"] == 25000000, r
    assert PK.entry_row(dict(e, business_pct=50), 2500)["deduct_micro"] == 12500000
    assert PK.entry_row(e, None)["deduct_micro"] == 0, "unknown share deducts nothing"
