"""The /settings/depreciation page and GET /v1/accounting/depreciation. All amounts are fake."""
import json
import sqlite3

import bloom_accounting_config as CF
import bloom_accounting_deprpage as DPG
from server_fixture import web  # noqa: F401

H = {"Host": "ledger.test", "Origin": "http://ledger.test"}
M4 = {"id": "m4", "display_name": "M4", "processor": "M4 Max", "ownership": "owned", "in_service": "2026-03-01",
      "business_mode": "auto_paid_hours", "purchase_cents": 100000, "depreciation_method": "macrs5", "bonus_bp": 0,
      "state": {"name": "California", "method": "straight_line", "life_months": 60}}
LEASED = {"id": "m5", "display_name": "M5", "processor": "M5 Ultra", "ownership": "leased", "in_service": "2026-10-01",
          "business_mode": "leased_100", "lease_monthly_cents": 20000, "lease_start": "2026-10-01"}


def db():
    d = sqlite3.connect(":memory:")
    CF.create_settings_table(d)
    return d


def test_data_has_schedules_state_and_keeps_leased():
    d = db()
    CF.set_setting(d, "machines", [M4, LEASED], "2026-03-01", 1)
    out = DPG.depreciation_data(d, {}, "2026-11-03")
    assert out["seeded"] is False and out["effective_from"] == "2026-03-01"
    assert [m["id"] for m in out["machines"]] == ["m4", "m5"]
    (a,) = out["assets"]
    assert [r["depreciation_cents"] for r in a["federal"]["years"]] == [20000, 32000, 19200, 11520, 11520, 5760]
    assert a["federal"]["years"][0]["business_bp"] is None
    assert a["state"]["name"] == "California" and sum(r["depreciation_cents"] for r in a["state"]["years"]) == 100000
    assert a["bonus_in_force_bp"] == 10000 and out["mid_quarter"][0]["required"] is False


def test_seed_from_profiles_when_no_records():
    prof = {"mini": {"display_name": "Mini", "model": "M4", "acquisition": "owned", "in_service": "2026-11-20",
                     "purchase_cents": 60000}, "rent": {"acquisition": "leased"}}
    out = DPG.depreciation_data(db(), prof, "2026-11-03")
    assert out["seeded"] is True and [m["id"] for m in out["machines"]] == ["mini"]
    assert out["effective_from"] == "2026-11-20" and out["mid_quarter"][0]["required"] is True
    legacy = DPG.seed_machines({"m4_in_service_date": "2025-06-01", "dep_method": "straight_line"}, {})
    assert legacy[0]["in_service"] == "2025-06-01" and legacy[0]["depreciation_method"] == "straight_line"


def test_routes_serve_page_and_data_and_accept_a_large_list(web):
    status, ctype, body = web("GET", "/settings/depreciation")
    assert status == 200 and ctype.startswith("text/html") and b"Save depreciation records" in body
    many = [dict(M4, id="m%d" % i, display_name="Mac %d" % i, manual_schedule_cents={str(2026 + y): 1000 for y in range(5)},
                 depreciation_method="manual") for i in range(30)]
    payload = json.dumps({"key": "machines", "value": many, "effective_from": "2026-03-01"}).encode()
    assert len(payload) > 4096
    assert web("POST", "/v1/accounting/settings", payload, headers=H)[0] == 200
    data = json.loads(web("GET", "/v1/accounting/depreciation")[2])
    assert len(data["assets"]) == 30 and data["assets"][0]["federal"]["years"][0]["depreciation_cents"] == 1000
    bad = json.dumps({"key": "machines", "value": [dict(M4, salvage_cents=-1)], "effective_from": "2026-03-01"}).encode()
    status, _, body = web("POST", "/v1/accounting/settings", bad, headers=H)
    assert status == 400 and "salvage" in json.loads(body)["error"]
