"""Frozen test: hardware depreciation uses only the business-use percent of each hardware entry. Fake numbers."""
import bloom_accounting_depr as DP
import bloom_accounting_fixed as FX

SET = {"m4_in_service_date": "2026-09-28", "dep_method": "straight_line", "dep_life_months": 60}


def hw(cents, pct, eid=1, machine="m4"):
    d = {"id": eid, "kind": "cost", "date": "2026-09-01", "amount_cents": cents, "category": "hardware", "machine_id": machine}
    if pct != "absent":
        d["business_pct"] = pct
    return d


def test_owned_depreciation_uses_the_business_part():
    got = FX.owned_depreciation_cents(SET, [hw(200000, 60), hw(50000, None, 2), hw(30001, "absent", 3)], "2026-10-01", "2026-10-31")
    want = sum(DP.depreciation_cents("straight_line", c, "2026-09-28", 60, "2026-10-01", "2026-10-31") for c in (120000, 50000, 30001))
    assert got == want


def test_machine_basis_uses_the_business_part():
    m = {"id": "m4", "ownership": "owned", "in_service": "2026-09-28"}
    assert FX.machine_basis_cents(m, [hw(100001, 50), hw(400, 25, 2), hw(9, "absent", 3)]) == 50000 + 100 + 9
    assert FX.entry_business_cents({"amount_cents": 999, "business_pct": 33}) == 329
