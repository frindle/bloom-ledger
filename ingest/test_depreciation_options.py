"""Depreciation options: MACRS tables, conventions, ADS, salvage, manual schedules, de minimis, disposal, state book,
Section 179 recapture and the mid-quarter test. All amounts are fake."""
import bloom_accounting_admin as AD
import bloom_accounting_depr as D
import bloom_accounting_machines as M
import bloom_accounting_schedule as S

INS = "2026-03-01"


def asset(**kw):
    a = {"basis_cents": 100000, "placed_in_service": INS}
    a.update(kw)
    return a


def year(a, y):
    return D.asset_depreciation_cents(a, "%d-01-01" % y, "%d-12-31" % y)


def years(a, y0=2026, n=8):
    return [year(a, y) for y in range(y0, y0 + n)]


def test_rates_match_the_irs_tables():
    assert D.macrs_rates_bp(5, 200) == (2000, 3200, 1920, 1152, 1152, 576)
    assert D.macrs_rates_bp(5, 200, "mid_quarter", 1) == (3500, 2600, 1560, 1101, 1101, 138)
    assert D.macrs_rates_bp(5, 200, "mid_quarter", 4) == (500, 3800, 2280, 1368, 1094, 958)
    assert D.macrs_rates_bp(5, 150) == (1500, 2550, 1785, 1666, 1666, 833)
    assert D.macrs_rates_bp(7, 200) == (1429, 2449, 1749, 1249, 893, 892, 893, 446)
    assert D.macrs_rates_bp(5, 100) == (1000, 2000, 2000, 2000, 2000, 1000)
    assert D.MACRS5_BP == D.macrs_rates_bp(5, 200)[:5]


def test_methods_and_conventions():
    assert years(asset(convention="mid_quarter", placed_in_service="2026-11-02"))[:6] == [5000, 38000, 22800, 13680, 10940, 9580]
    assert years(asset(method="macrs_150db"))[:6] == [15000, 25500, 17850, 16660, 16660, 8330]
    assert years(asset(method="ads", life_months=60))[:6] == [10000, 20000, 20000, 20000, 20000, 10000]
    assert sum(years(asset(**{"class": "7-year"}), n=10)) == 100000


def test_monthly_periods_add_up_to_the_year():
    a = asset(convention="mid_quarter", method="macrs_150db")
    parts = [D.asset_depreciation_cents(a, "2027-%02d-01" % m, "2027-%02d-01" % (m + 1)) - D.asset_depreciation_cents(
        a, "2027-%02d-01" % (m + 1), "2027-%02d-01" % (m + 1)) for m in range(1, 12)]
    assert sum(parts) + D.asset_depreciation_cents(a, "2027-12-01", "2027-12-31") == year(a, 2027)


def test_straight_line_salvage_and_de_minimis():
    a = asset(method="straight_line", life_months=36, salvage_cents=10000)
    assert D.asset_depreciation_cents(a, "2026-01-01", "2040-12-31") == 90000
    dm = asset(method="de_minimis", basis_cents=24000)
    assert D.asset_depreciation_cents(dm, INS, INS) == 24000 and year(dm, 2027) == 0
    assert any("not on Form 4562" in f for f in S.asset_flags(dm))
    assert any("$2,500" in f for f in S.asset_flags(asset(method="de_minimis", basis_cents=300000)))


def test_manual_schedule_is_used_verbatim():
    a = asset(method="manual", manual_schedule_cents={"2026": 55555, "2028": 44445}, section179_cents=99999, bonus_bp=10000)
    assert years(a, n=4) == [55555, 0, 44445, 0]
    assert D.asset_depreciation_cents(a, "2026-01-01", "2026-06-30") + D.asset_depreciation_cents(a, "2026-07-01", "2026-12-31") == 55555


def test_partial_section179_then_bonus_then_macrs():
    a = asset(section179_cents=30000, bonus_bp=5000)
    first = 30000 + 35000
    assert year(a, 2026) == first + 35000 * 2000 // 10000
    assert sum(years(a)) == 100000


def test_disposal_stops_depreciation_and_reports_gain():
    a = asset(disposed_on="2028-06-30", disposal_price_cents=60000)
    ys = years(a)
    assert ys[:2] == [20000, 32000] and ys[2] == 19200 // 2 and ys[3:] == [0] * 5
    d = S.disposal(a)
    taken = 20000 + 32000 + 9600
    assert d["depreciation_taken_cents"] == taken and d["adjusted_basis_cents"] == 100000 - taken
    assert d["gain_cents"] == 60000 - (100000 - taken) and d["recapture_1245_cents"] == d["gain_cents"]
    loss = S.disposal(asset(disposed_on="2027-03-01", disposal_price_cents=0))
    assert loss["gain_cents"] < 0 and loss["recapture_1245_cents"] == 0
    assert year(asset(disposed_on="2026-12-01", bonus_bp=10000), 2026) == 0  # no bonus or MACRS in a same-year disposal
    sl = asset(method="straight_line", life_months=60, disposed_on="2027-01-01")
    assert D.asset_depreciation_cents(sl, "2027-01-02", "2040-12-31") == 0


def test_state_book_without_bonus():
    a = asset(bonus_bp=10000, state={"name": "California", "bonus_bp": 0, "section179_cents": 0})
    st = S.state_asset(a)
    assert year(a, 2026) == 100000 and year(st, 2026) == 20000 and S.state_asset(asset()) is None


def test_schedule_rows_and_remaining_basis():
    a = asset(business_use_bp={"2027": 5000})
    sch = S.asset_schedule(a, default_bp=9000)
    assert [r["year"] for r in sch["years"]] == list(range(2026, 2032))
    assert sch["total_cents"] == 100000 and sch["years"][-1]["remaining_basis_cents"] == 0
    assert sch["years"][0]["business_cents"] == 18000 and sch["years"][1]["business_cents"] == 16000


def test_bonus_rate_in_force_and_flag():
    assert [S.bonus_in_force_bp(d) for d in ("2022-06-01", "2023-06-01", "2024-06-01", "2025-01-10", "2026-09-28")] == \
        [10000, 8000, 6000, 4000, 10000]
    assert any("elect out" in f for f in S.asset_flags(asset()))
    assert not any("elect out" in f for f in S.asset_flags(asset(bonus_bp=0)))


def test_section179_recapture_when_use_drops():
    a = asset(section179_cents=50000, business_use_bp={"2026": 10000, "2027": 9000, "2028": 4000})
    r = S.section179_recapture(a)
    assert r["year"] == 2028 and r["recapture_cents"] == 50000 - (10000 + 16000)
    assert any("recaptured" in f for f in S.asset_flags(a))
    assert S.section179_recapture(asset(section179_cents=50000)) is None


def test_mid_quarter_test():
    late = asset(placed_in_service="2026-11-15", basis_cents=60000)
    early = asset(basis_cents=40000)
    assert S.mid_quarter_test([late, early], 2026)["required"] is True
    assert S.mid_quarter_test([asset(placed_in_service="2026-11-15", basis_cents=40000), asset(basis_cents=60000)], 2026)["required"] is False


OWNED = {"id": "m4", "display_name": "M4", "processor": "M4 Max", "ownership": "owned", "in_service": INS,
         "business_mode": "auto_paid_hours", "purchase_cents": 100000, "depreciation_method": "macrs5"}


def test_validation_of_new_fields():
    good = dict(OWNED, convention="mid_quarter", **{"class": "7-year"}, salvage_cents=100, disposed_on="2028-01-01",
                disposal_price_cents=0, life_months=72, state={"name": "CA", "bonus_bp": 0})
    assert M.validate_machine(good) == {}
    bad = dict(OWNED, depreciation_method="manual", salvage_cents=200000, disposed_on="2020-01-01", state={"bonus": 1})
    assert sorted(M.validate_machine(bad)) == ["disposed_on", "manual_schedule_cents", "salvage_cents", "state"]
    assert "depreciation_method" in M.validate_machine(dict(OWNED, depreciation_method="de_minimis", purchase_cents=300000))
    assert AD.machines_errors([OWNED, OWNED]) == ["m4: listed twice"]
    assert AD.machines_errors("x") == ["machines must be a list"]
