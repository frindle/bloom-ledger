"""Frozen test: validate_machine returns per-field errors for owned and leased machines."""
import bloom_accounting_machines as M

OWNED = {"id": "m4max", "display_name": "M4 Max", "processor": "Apple M4 Max", "ownership": "owned", "in_service": "2026-10-01",
         "business_mode": "auto_paid_hours", "purchase_cents": 322565, "depreciation_method": "straight_line", "watts": 90}
LEASED = {"id": "m5ultra", "display_name": "M5 Ultra", "processor": "Apple M5 Ultra", "ownership": "leased", "in_service": "2026-11-15",
          "business_mode": "leased_100", "lease_monthly_cents": 13735, "lease_start": "2026-11-15"}


def test_valid_machines_have_no_errors():
    assert M.validate_machine(OWNED) == {}
    assert M.validate_machine(LEASED) == {}
    assert M.validate_machine(dict(OWNED, watts=None, address="studio.local", plug_address="10.0.0.5", plug_type="shelly")) == {}


def test_each_bad_field_is_named():
    bad = M.validate_machine({"id": "Bad Id", "display_name": " ", "processor": "", "ownership": "borrowed",
                              "in_service": "2026-13-01", "business_mode": "x", "watts": 0})
    assert sorted(bad) == ["business_mode", "display_name", "id", "in_service", "ownership", "processor", "watts"]
    assert all(isinstance(v, str) and v for v in bad.values())
    assert M.validate_machine("nope") == {"form": "not an object"}


def test_owned_and_leased_need_their_own_fields():
    assert sorted(M.validate_machine({k: v for k, v in OWNED.items() if k not in ("purchase_cents", "depreciation_method")})) == ["depreciation_method", "purchase_cents"]
    assert sorted(M.validate_machine(dict(OWNED, purchase_cents=True))) == ["purchase_cents"]
    assert sorted(M.validate_machine({k: v for k, v in LEASED.items() if k not in ("lease_monthly_cents", "lease_start")})) == ["lease_monthly_cents", "lease_start"]
    assert sorted(M.validate_machine(dict(LEASED, lease_start="soon", lease_monthly_cents=-5))) == ["lease_monthly_cents", "lease_start"]
    assert M.validate_machine(dict(OWNED, watts=5001)) == {"watts": M.validate_machine(dict(OWNED, watts=5001))["watts"]}
