"""Frozen test: validate_purchase returns per-field errors for the top-level purchase fields."""
import bloom_accounting_purchases as P

OK = {"merchant": "Example Store", "order_number": "A-1001", "purchase_date": "2026-10-20", "note": None,
      "replaces_id": None, "items": [{"description": "cable"}]}


def test_valid_purchase_has_no_errors():
    assert P.validate_purchase(OK) == {}
    assert P.validate_purchase(dict(OK, order_number=None, note="gift", replaces_id=7)) == {}
    assert P.validate_purchase("nope") == {"form": "not an object"}


def test_each_bad_field_is_named():
    bad = P.validate_purchase({"merchant": " ", "order_number": 5, "purchase_date": "2026-02-30", "note": 3,
                               "replaces_id": 0, "items": []})
    assert sorted(bad) == ["items", "merchant", "note", "order_number", "purchase_date", "replaces_id"]
    assert all(isinstance(v, str) and v for v in bad.values())
    assert sorted(P.validate_purchase(dict(OK, merchant="m" * 81, order_number="o" * 61, note="n" * 501))) == ["merchant", "note", "order_number"]
    assert sorted(P.validate_purchase(dict(OK, replaces_id=True, items=[{}] * 51))) == ["items", "replaces_id"]
    assert sorted(P.validate_purchase(dict(OK, items="x", purchase_date=None))) == ["items", "purchase_date"]
