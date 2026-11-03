"""Frozen test: validate_entry checks the tax-record fields vendor, purpose and business_pct."""
import bloom_accounting_entries as E


def good(**kw):
    e = {"kind": "cost", "date": "2026-10-20", "amount_cents": 1234, "category": "hardware"}
    e.update(kw)
    return e


def check_record_fields_accepted():
    assert E.validate_entry(good(vendor="B&H Photo", purpose="Cooling for the M4 provider", business_pct=100)) is None
    assert E.validate_entry(good(business_pct=1)) is None and E.validate_entry(good(business_pct=60)) is None
    assert E.validate_entry(good(vendor=None, purpose=None, business_pct=None)) is None
    assert E.validate_entry(good(vendor="x" * 200)) is None


def test_bad_vendor_and_purpose():
    for bad in (5, "", "   ", "x" * 201, ["a"]):
        assert E.validate_entry(good(vendor=bad)) == "bad vendor", bad
        assert E.validate_entry(good(purpose=bad)) == "bad purpose", bad


def test_bad_business_pct_and_good_records_pass():
    for bad in (0, 101, -5, True, False, 50.0, "50"):
        assert E.validate_entry(good(business_pct=bad)) == "bad business_pct", bad
    check_record_fields_accepted()


def test_order_after_existing_checks():
    assert E.validate_entry(good(amount_cents=0, vendor=5)) == "bad amount"
    assert E.validate_entry(good(note=3, vendor=5)) == "bad note"
    assert E.validate_entry(good(vendor=5, purpose=5, business_pct=0)) == "bad vendor"
    assert E.validate_entry(good(purpose=5, business_pct=0)) == "bad purpose"


def test_docstring_names_the_fields():
    doc = E.validate_entry.__doc__ or ""
    for word in ("vendor", "purpose", "business_pct", "200", "100"):
        assert word in doc, word
