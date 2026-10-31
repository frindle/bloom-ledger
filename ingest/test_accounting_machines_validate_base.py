"""Frozen test: validate_machine returns per-field errors for the common machine fields."""
import bloom_accounting_machines as M

OWNED = {"id": "m4max", "display_name": "M4 Max", "processor": "Apple M4 Max", "ownership": "owned", "in_service": "2026-10-01",
         "business_mode": "auto_paid_hours", "purchase_cents": 322565, "depreciation_method": "straight_line", "watts": 90}


def test_valid_common_fields_have_no_errors():
    assert M.validate_machine(OWNED) == {}
    assert M.validate_machine(dict(OWNED, watts=None, address="studio.local", plug_address="10.0.0.5", plug_type="shelly")) == {}
    assert M.validate_machine(dict(OWNED, ownership="leased", business_mode="leased_100", lease_monthly_cents=13735, lease_start="2026-11-15")) == {}


def test_each_bad_field_is_named():
    bad = M.validate_machine({"id": "Bad Id", "display_name": " ", "processor": "", "ownership": "borrowed",
                              "in_service": "2026-13-01", "business_mode": "x", "watts": 0})
    assert sorted(bad) == ["business_mode", "display_name", "id", "in_service", "ownership", "processor", "watts"]
    assert all(isinstance(v, str) and v for v in bad.values())
    assert M.validate_machine("nope") == {"form": "not an object"}
    assert sorted(M.validate_machine(dict(OWNED, watts=5001, id="x" * 33, display_name="n" * 61))) == ["display_name", "id", "watts"]
    assert sorted(M.validate_machine(dict(OWNED, watts=True))) == ["watts"]
