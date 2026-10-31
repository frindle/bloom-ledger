"""Frozen test: owned machines need a price and method, leased machines a monthly lease and start."""
import bloom_accounting_machines as M

OWNED = {"id": "m4max", "display_name": "M4 Max", "processor": "Apple M4 Max", "ownership": "owned", "in_service": "2026-10-01",
         "business_mode": "auto_paid_hours", "purchase_cents": 322565, "depreciation_method": "straight_line", "watts": 90}
LEASED = {"id": "m5ultra", "display_name": "M5 Ultra", "processor": "Apple M5 Ultra", "ownership": "leased", "in_service": "2026-11-15",
          "business_mode": "leased_100", "lease_monthly_cents": 13735, "lease_start": "2026-11-15"}


def test_owned_needs_price_and_method():
    assert M.validate_machine(OWNED) == {}
    assert sorted(M.validate_machine({k: v for k, v in OWNED.items() if k not in ("purchase_cents", "depreciation_method")})) == ["depreciation_method", "purchase_cents"]
    assert sorted(M.validate_machine(dict(OWNED, purchase_cents=True, depreciation_method="guess"))) == ["depreciation_method", "purchase_cents"]
    assert M.validate_machine(dict(OWNED, purchase_cents=0)).keys() == {"purchase_cents"}


def test_leased_needs_monthly_and_start():
    assert M.validate_machine(LEASED) == {}
    assert sorted(M.validate_machine({k: v for k, v in LEASED.items() if k not in ("lease_monthly_cents", "lease_start")})) == ["lease_monthly_cents", "lease_start"]
    assert sorted(M.validate_machine(dict(LEASED, lease_start="soon", lease_monthly_cents=-5))) == ["lease_monthly_cents", "lease_start"]
    assert M.validate_machine(dict(LEASED, purchase_cents=None)) == {}
