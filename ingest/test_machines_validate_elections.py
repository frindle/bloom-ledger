"""Frozen test: validate_machine checks the optional tax fields (class, convention, elections, yearly business use, lease months). Fake numbers."""
import bloom_accounting_machines as M

OWNED = {"id": "box1", "display_name": "Box One", "processor": "Test CPU", "ownership": "owned", "in_service": "2026-03-01",
         "business_mode": "auto_paid_hours", "purchase_cents": 100000, "depreciation_method": "macrs5"}
LEASED = {"id": "box2", "display_name": "Box Two", "processor": "Test CPU", "ownership": "leased", "in_service": "2026-03-01",
          "business_mode": "leased_100", "lease_monthly_cents": 5000, "lease_start": "2026-03-01"}


def test_bad_class_convention_and_elections_are_named():
    assert M.validate_machine(OWNED) == {}
    good = dict(OWNED, **{"class": "5-year"}, convention="half_year", section179_cents=0, bonus_bp=10000,
                business_use_bp={"2026": 5000, "2027": 10000})
    assert M.validate_machine(good) == {} and M.validate_machine(dict(OWNED, bonus_bp=None, business_use_bp=None)) == {}
    bad = dict(OWNED, **{"class": "40-year"}, convention="monthly", section179_cents=-1, bonus_bp=10001)
    assert sorted(M.validate_machine(bad)) == ["bonus_bp", "class", "convention", "section179_cents"]
    assert sorted(M.validate_machine(dict(OWNED, section179_cents=True, bonus_bp=True))) == ["bonus_bp", "section179_cents"]
    assert M.validate_machine(dict(OWNED, section179_cents=1.5)).keys() == {"section179_cents"}


def test_bad_yearly_business_use_and_lease_months():
    assert M.validate_machine(dict(LEASED, lease_months=36)) == {}
    for ub in ("half", {"26": 5000}, {"2026": 10001}, {"2026": -1}, {"2026": True}, {"2026": 50.5}):
        assert M.validate_machine(dict(OWNED, business_use_bp=ub)).keys() == {"business_use_bp"}, ub
    assert M.validate_machine(dict(LEASED, lease_months=0)).keys() == {"lease_months"}
    assert M.validate_machine(dict(LEASED, lease_months=True)).keys() == {"lease_months"}
