"""Frozen test: bloom_accounting_entries.validate_entry (synthetic)."""
import bloom_accounting_entries as E


def good(**kw):
    e = {"kind": "cost", "date": "2026-10-20", "amount_cents": 1234, "category": "software"}
    e.update(kw)
    return e


def test_valid_entries_pass():
    assert E.validate_entry(good()) is None
    assert E.validate_entry(good(kind="receipt", machine_id="m1", note="x", category="hardware")) is None


def test_error_strings_and_order():
    assert E.validate_entry([]) == "not an object"
    assert E.validate_entry(good(kind="gift")) == "bad kind"
    assert E.validate_entry(good(date="2026-13-01")) == "bad date"
    assert E.validate_entry(good(date="20261020")) == "bad date"
    assert E.validate_entry(good(amount_cents=0)) == "bad amount"
    assert E.validate_entry(good(amount_cents=True)) == "bad amount"
    assert E.validate_entry(good(amount_cents=1.5)) == "bad amount"
    assert E.validate_entry(good(category="boat")) == "bad category"
    assert E.validate_entry(good(kind="gift", date="x")) == "bad kind"


def test_optional_fields_checked_when_present():
    assert E.validate_entry(good(machine_id="")) == "bad machine_id"
    assert E.validate_entry(good(machine_id=5)) == "bad machine_id"
    assert E.validate_entry(good(note=3)) == "bad note"
    assert E.validate_entry(good(machine_id=None, note=None)) is None
