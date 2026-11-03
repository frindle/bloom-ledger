"""Frozen test: bloom_accounting_packet builds the year-end packet data from the ledger and agrees with the tax report. Fake data."""
import datetime as dt
import bloom_accounting_packet as PK
import sqlite3

import bloom_accounting_config as CF
import bloom_accounting_depr as DP
import bloom_accounting_entries as AE
import bloom_accounting_index as AX
import bloom_accounting_tax as TX

SCHED = [{"months": list(range(1, 13)), "periods": [{"start": "00:00", "end": "24:00", "rate": "0.1"}]}]


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def mod():
    return PK


def make():
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, completion_tokens, source_machine) VALUES ('e', ?, 2000000, 'job', 9, 'm4')",
               (utc(2025, 10, 20, 20, 0),))
    for m, tok, other in ((0, 3, 0), (1, 0, 0), (2, 0, 1)):
        db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, other_work, tokens_delta) VALUES ('m4', ?, 1000, 60, 1, ?, ?)",
                   (utc(2025, 10, 20, 20, m), other, tok))
    db.commit()
    vals = {"rate_schedule": SCHED, "rate_adder_usd_per_kwh": "0", "universal_charge_usd_per_kwh": "0", "county_fee_pct": "0",
            "m4_machine_id": "m4", "local_timezone": "UTC", "m4_in_service_date": "2025-03-01", "dep_method": "straight_line",
            "dep_life_months": 60, "m5_lease_monthly_cents": 1000, "m5_lease_months": 36, "m5_lease_start": "2025-01-01"}
    for k, v in vals.items():
        CF.set_setting(db, k, v, "2024-01-01", 1)
    E = [("cost", "2025-02-10", 182600, "hardware", "Apple", "Mac Studio for inference", None),   # 1
         ("cost", "2025-04-01", 2400, "software", "Tools & <Co>", "API access", 50),               # 2
         ("cost", "2025-10-05", 8000, "internet", "ISP", "Home internet", None),                   # 3
         ("cost", "2025-10-06", 5000, "electricity", "Utility", "Power bill", None),               # 4
         ("receipt", "2025-10-07", 3000, "other", "Client", "Consulting", None),                   # 5
         ("cost", "2025-10-08", 999, "supplies", "Store", "Cables", None),                         # 6 voided below
         ("cost", "2025-11-01", 1500, "other", "Host", "Domain", None),                            # 7
         ("cost", "2024-12-01", 50000, "hardware", "Shop", "Drive", None),                         # 8
         ("cost", "2026-01-05", 700, "software", "Next", "Next year", None)]                       # 9
    for kind, d, cents, cat, vendor, purpose, pct in E:
        e = {"kind": kind, "date": d, "amount_cents": cents, "category": cat, "vendor": vendor, "purpose": purpose}
        if pct is not None:
            e["business_pct"] = pct
        AE.add_entry(db, e, 1)
    AE.void_entry(db, 6, 2)
    AE.attach_receipt(db, 7, "entry-7-0123456789abcdef.pdf")
    return db


def test_asset_rows():
    st = {"m4_in_service_date": "2025-03-01", "dep_method": "straight_line", "dep_life_months": 60}
    es = [{"id": 1, "kind": "cost", "category": "hardware", "date": "2025-02-10", "amount_cents": 100000, "business_pct": 50, "vendor": "A"},
          {"id": 2, "kind": "cost", "category": "software", "date": "2025-02-10", "amount_cents": 500},
          {"id": 3, "kind": "cost", "category": "hardware", "date": "2025-06-01", "amount_cents": 20000},
          {"id": 4, "kind": "cost", "category": "hardware", "date": "2026-01-02", "amount_cents": 20000}]
    out = PK.asset_rows(st, es, 2025, "2026-02-01")
    assert [a["id"] for a in out] == [1, 3], out
    assert out[0]["basis_cents"] == 50000 and out[0]["placed_in_service"] == "2025-03-01" and out[0]["vendor"] == "A"
    assert out[1]["placed_in_service"] == "2025-06-01" and out[1]["purpose"] is None and out[1]["method"] == "straight_line"
    assert out[0]["year_cents"] == DP.depreciation_cents("straight_line", 50000, "2025-03-01", 60, "2025-01-01", "2025-12-31") > 0
    assert PK.asset_rows(st, es, 2025, "2025-04-30")[0]["year_cents"] == DP.depreciation_cents(
        "straight_line", 50000, "2025-03-01", 60, "2025-01-01", "2025-04-30")
    assert [a["year_cents"] for a in PK.asset_rows(st, es, 2026, "2025-12-31")] == [0, 0, 0]
    assert PK.asset_rows(dict(st, m4_in_service_date=None), es, 2025, "2025-12-31")[0]["placed_in_service"] == "2025-02-10"


def test_entry_rows():
    P = mod()
    db = make()
    d = P.packet_data(db, 2025, "2026-02-01")
    rows = {r["id"]: r for r in d["entries"]}
    assert sorted(rows) == [1, 2, 3, 4, 5, 7], sorted(rows)
    assert rows[1]["line"] == "13" and rows[1]["deduct_micro"] is None and rows[1]["needs"] == ["receipt"]
    assert rows[2]["line"] == "18" and rows[2]["business_pct"] == 50 and rows[2]["deduct_micro"] == 12000000
    assert rows[2]["vendor"] == "Tools & <Co>" and rows[2]["purpose"] == "API access"
    oct_bp = [m for m in TX.build_tax(db, 2025)["months"] if m["month"] == "2025-10"][0]["bp"]
    assert oct_bp == 3333
    assert rows[3]["line"] == "25" and rows[3]["deduct_micro"] == 8000 * 3333 // 10000 * 10000
    assert rows[4]["line"] == "25" and rows[4]["deduct_micro"] == 0, "metered power already counts the electricity bill"
    assert rows[5]["kind"] == "receipt" and rows[5]["line"] == "6" and rows[5]["deduct_micro"] == 30000000
    assert rows[7]["line"] == "27a" and rows[7]["receipt"] == "entry-7-0123456789abcdef.pdf" and rows[7]["needs"] == []
    assert P.entry_row({"id": 9, "kind": "cost", "date": "2025-05-01", "amount_cents": 100, "category": "supplies"}, None)["needs"] == [
        "vendor", "purpose", "receipt"]


def test_lines_agree_with_tax_report():
    P = mod()
    db = make()
    d = P.packet_data(db, 2025, "2026-02-01")
    t = TX.build_tax(db, 2025)["totals"]
    assert [l["line"] for l in d["lines"]] == ["1", "6", "13", "16b", "18", "20a", "22", "25", "27a"]
    v = {l["line"]: l["micro"] for l in d["lines"]}
    assert v["1"] == t["income_micro"] == 2000000 and v["6"] == t["other_income_micro"] == 30000000
    assert v["13"] == t["depreciation_business_micro"] and v["20a"] == t["lease_business_micro"]
    assert v["18"] == 12000000 and v["22"] == 0 and v["27a"] == 15000000
    assert v["25"] == t["power_business_micro"] + 8000 * 3333 // 10000 * 10000
    assert sum(v[k] for k in ("13", "16b", "18", "20a", "22", "25", "27a")) == t["expenses_micro"] == d["expenses_micro"]
    assert d["net_micro"] == t["net_micro"] and d["year"] == 2025 and d["prepared"] == "2026-02-01"
    none = P.packet_lines(dict(t, power_business_micro=None, lease_business_micro=None), d["entries"])
    nv = {l["line"]: l["micro"] for l in none}
    assert nv["25"] is None and nv["20a"] is None and nv["18"] == 12000000


def test_assets_use_and_flags():
    P = mod()
    db = make()
    d = P.packet_data(db, 2025, "2026-02-01")
    assert [a["id"] for a in d["assets"]] == [8, 1], d["assets"]
    a8, a1 = d["assets"]
    assert a8["placed_in_service"] == "2025-03-01" and a1["placed_in_service"] == "2025-03-01"
    assert a1["basis_cents"] == 182600 and a1["method"] == "straight_line" and a1["vendor"] == "Apple"
    assert a1["year_cents"] == DP.depreciation_cents("straight_line", 182600, "2025-03-01", 60, "2025-01-01", "2025-12-31")
    assert a1["year_cents"] > 0
    early = P.packet_data(db, 2025, "2025-06-30")["assets"][1]["year_cents"]
    assert early == DP.depreciation_cents("straight_line", 182600, "2025-03-01", 60, "2025-01-01", "2025-06-30") < a1["year_cents"]
    assert P.packet_data(db, 2026, "2025-12-31")["assets"][1]["year_cents"] == 0
    assert d["use"] == {"business_bp": 3333, "minutes": 3, "kwh": 3.0}
    assert d["flags"] == CF.effective_settings(db, "2025-12-31")["flags"]
    assert "not tax advice" in d["disclaimer"]
