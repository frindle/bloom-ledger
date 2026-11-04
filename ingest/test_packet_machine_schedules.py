"""The tax packet uses machine records: the same engine numbers, a year-by-year schedule, the state book and notes. Fake data."""
import bloom_accounting_config as CF
import bloom_accounting_depr as DP
import bloom_accounting_packet as PK
import bloom_accounting_tax as TX
from test_packet_data import make

M4 = {"id": "m4", "display_name": "Studio", "processor": "M4 Max", "ownership": "owned", "in_service": "2025-03-01",
      "business_mode": "auto_paid_hours", "purchase_cents": 100000, "depreciation_method": "macrs5",
      "section179_cents": 20000, "state": {"name": "California", "section179_cents": 0, "bonus_bp": 0}}


def test_packet_follows_machine_records():
    db = make()
    CF.set_setting(db, "machines", [M4], "2024-01-01", 2)
    CF.set_setting(db, "entry_machine_links", {"1": "other", "8": "other"}, "2024-01-01", 2)
    d = PK.packet_data(db, 2026, "2027-02-01")
    a = d["assets"]
    assert [r["id"] for r in a] == ["m4"] and a[0]["basis_cents"] == 100000
    asset = {"basis_cents": 100000, "placed_in_service": "2025-03-01", "method": "macrs5", "section179_cents": 20000}
    assert a[0]["year_cents"] == DP.asset_depreciation_cents(asset, "2026-01-01", "2026-12-31") == 80000 * 3200 // 10000
    sc = d["schedules"][0]
    assert [r["year"] for r in sc["years"]] == [2025, 2026]
    assert sc["years"][0]["depreciation_cents"] == 20000 + 16000 and sc["years"][1]["remaining_basis_cents"] == 100000 - 36000 - 25600
    assert sc["state"]["name"] == "California" and sc["state"]["years"][0]["depreciation_cents"] == 20000
    assert any("elect out" in n for n in d["dep_notes"])
    assert d["flags"] == CF.effective_settings(db, "2026-12-31")["flags"]
    h = PK.packet_html(d)
    assert "<h3>Studio: MACRS 200% declining balance, 5-year, half-year</h3>" in h and "California" in h and "Remaining basis" in h
    assert "elect out" in h
    tax = TX.build_tax(db, 2026)
    assert tax["totals"]["depreciation_business_micro"] is not None
