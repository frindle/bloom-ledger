"""Monthly tally: reuses the tax report's figures, split by machine, in integer cents. Fake numbers."""
import datetime as dt
import json
import sqlite3

import pytest

import bloom_accounting_config as CF
import bloom_accounting_entries as AE
import bloom_accounting_index as AX
import bloom_accounting_tally as TL
import bloom_accounting_tax as TX

SCHED = [{"months": list(range(1, 13)), "periods": [{"start": "00:00", "end": "24:00", "rate": "0.1234"}]}]
OWNED = {"id": "m4", "ownership": "owned", "in_service": "2026-09-28", "depreciation_method": "straight_line", "purchase_cents": 182600,
         "display_name": "Studio"}
LEASED = {"id": "m5", "ownership": "leased", "lease_start": "2026-10-01", "lease_monthly_cents": 36501, "display_name": "M5"}
TZ = "America/Los_Angeles"


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def make():
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    n = 0
    for mach in ("m4", "m5"):
        for mon in (10, 11):
            for i, micro in enumerate((1234567, 777777, 3)):
                n += 1
                db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, completion_tokens, source_machine) VALUES (?,?,?,?,?,?)",
                           ("e%d" % n, utc(2026, mon, 5 + i, 20, 0), micro * (1 if mach == "m4" else 2), "job", 5, mach))
            for minute in range(4):
                db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, other_work, tokens_delta) VALUES (?,?,?,60,1,0,?)",
                           (mach, utc(2026, mon, 5, 20, minute), 1111.1 * (1 + minute), 3 if minute < 3 else 0))
    db.execute("INSERT INTO account_totals (at, count, total_micro_usd, available_micro_usd, withdrawable_micro_usd)"
               " VALUES ('2026-10-13T19:13:39Z', 1, 16515444, 12345678, 9999999)")
    db.execute("INSERT INTO account_totals (at, count, total_micro_usd, available_micro_usd, withdrawable_micro_usd)"
               " VALUES ('2026-11-03T00:00:00Z', 1, 20000000, 15000019, 14000001)")
    db.commit()
    vals = {"rate_schedule": SCHED, "rate_adder_usd_per_kwh": "0.00096", "universal_charge_usd_per_kwh": "0.00039", "county_fee_pct": "5",
            "m4_in_service_date": "2026-09-28", "machines": [OWNED, LEASED]}
    for k, v in vals.items():
        CF.set_setting(db, k, v, "2026-01-01", 1)
    AE.add_entry(db, {"kind": "cost", "date": "2026-10-05", "amount_cents": 1299, "category": "software", "machine_id": "m4",
                      "vendor": "Acme", "purpose": "tools", "business_pct": 70}, 1)
    AE.add_entry(db, {"kind": "cost", "date": "2026-10-06", "amount_cents": 4001, "category": "internet", "machine_id": None}, 1)
    AE.add_entry(db, {"kind": "receipt", "date": "2026-11-07", "amount_cents": 501, "category": "other", "machine_id": "m5"}, 1)
    AE.add_entry(db, {"kind": "cost", "date": "2026-11-08", "amount_cents": 250000, "category": "electricity", "machine_id": None}, 1)
    gone = AE.add_entry(db, {"kind": "cost", "date": "2026-10-09", "amount_cents": 77777, "category": "supplies", "machine_id": "m4"}, 1)
    AE.void_entry(db, gone, 2)
    return db


NOW = utc(2027, 1, 1, 0, 0)


def total_of(t, col):
    return sum(r[col] for r in t["machines"])


def test_month_equals_tax_report_row():
    db = make()
    rep = {m["month"]: m for m in TX.build_tax(db, 2026)["months"]}
    for month in ("2026-10", "2026-11"):
        t, row = TL.build_month(db, month, NOW), rep[month]
        want = {"earnings_cents": row["income_micro"], "other_income_cents": row["other_income_micro"],
                "power_cost_cents": row["power_business_micro"], "depreciation_cents": row["depreciation_business_micro"],
                "lease_cents": row["lease_business_micro"], "entries_deductible_cents": row["entries_business_micro"]}
        for col, micro in want.items():
            assert t["totals"][col] == total_of(t, col) == micro // 10000, (month, col)
        assert t["totals"]["power_cost_cents"] > 0 and t["totals"]["lease_cents"] > 0
        assert all(isinstance(r[c], int) for r in t["machines"] for c in TL.COLUMNS)


def test_twelve_months_sum_to_year_totals():
    db = make()
    rep = TX.build_tax(db, 2026)
    tallies = [TL.build_month(db, "2026-%02d" % m, NOW) for m in range(1, 13)]
    for col, key in (("earnings_cents", "income_micro"), ("other_income_cents", "other_income_micro"),
                     ("power_cost_cents", "power_business_micro"), ("depreciation_cents", "depreciation_business_micro"),
                     ("lease_cents", "lease_business_micro"), ("entries_deductible_cents", "entries_business_micro")):
        assert sum(t["totals"][col] for t in tallies) == sum(m[key] // 10000 for m in rep["months"]), col
        # each cent is within one cent per month of the year total in micro-USD
        assert abs(sum(t["totals"][col] for t in tallies) * 10000 - rep["totals"][key]) < 12 * 10000


def test_entries_and_receipt_meaning():
    db = make()
    oct_, nov = TL.build_month(db, "2026-10", NOW), TL.build_month(db, "2026-11", NOW)
    ids = [e["id"] for r in oct_["machines"] for e in r["entries"]]
    assert len(ids) == 2 and 77777 not in [e["amount_cents"] for r in oct_["machines"] for e in r["entries"]]  # voided one excluded
    m4 = next(r for r in oct_["machines"] if r["machine_id"] == "m4")
    assert m4["entries"][0]["deductible_cents"] == 1299 * 70 // 100 and m4["entries"][0]["effect"] == "expense"
    shared = next(r for r in oct_["machines"] if r["shared"])
    assert shared["entries"][0]["category"] == "internet" and shared["entries"][0]["deductible_cents"] > 0
    m5 = next(r for r in nov["machines"] if r["machine_id"] == "m5")
    rec = m5["entries"][0]
    assert rec["kind"] == "receipt" and rec["effect"] == "income" and rec["deductible_cents"] == 0
    assert m5["other_income_cents"] == 501 and total_of(oct_, "other_income_cents") == 0
    elec = next(e for r in nov["machines"] for e in r["entries"] if e["category"] == "electricity")
    assert elec["effect"] == "metered_power" and elec["deductible_cents"] == 0


def test_effective_dated_rule_change_mid_year():
    db = make()
    before = TL.build_month(db, "2026-10", NOW)["totals"]["power_cost_cents"]
    CF.set_setting(db, "write_off", {"power": "none"}, "2026-11-01", 9)
    assert TL.build_month(db, "2026-10", NOW)["totals"]["power_cost_cents"] == before > 0
    assert TL.build_month(db, "2026-11", NOW)["totals"]["power_cost_cents"] == 0


def snap(db, ts):
    db.execute("INSERT INTO account_totals (at, count) VALUES (?, 1)", (dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),))
    db.commit()


def test_final_flag():
    db = make()
    end_oct = utc(2026, 11, 1, 7, 0)                                       # local midnight, Nov 1 (PDT)
    assert TL.build_month(db, "2026-10", NOW)["final"] is True             # make() holds a 2026-11-03 snapshot
    assert TL.build_month(db, "2026-10", end_oct - 1)["final"] is False    # month not over yet
    clean = sqlite3.connect(":memory:")
    AX.create_schema(clean)
    assert TL.build_month(clean, "2026-10", NOW)["final"] is False         # no snapshot at all
    snap(clean, end_oct + 300)                                             # inside the settle window
    assert TL.build_month(clean, "2026-10", NOW)["final"] is False
    snap(clean, end_oct + 901)
    assert TL.build_month(clean, "2026-10", NOW)["final"] is True


def test_current_month_not_final_and_unsettled_past_month():
    db = make()
    db.execute("INSERT INTO account_totals (at, count) VALUES ('2026-12-31T00:00:00Z', 1)")
    db.commit()
    assert TL.build_month(db, "2026-12", utc(2026, 12, 15, 0, 0))["final"] is False
    db2 = make()
    assert TL.build_month(db2, "2026-11", NOW)["final"] is False           # archive last settled 2026-11-03, before Dec 1


def test_balances_latest_at_or_before_month_end():
    db = make()
    b = TL.build_month(db, "2026-10", NOW)["balances"]
    assert b == {"as_of": "2026-10-13T19:13:39Z", "available_cents": 1234, "withdrawable_cents": 999}
    assert TL.build_month(db, "2026-11", NOW)["balances"]["as_of"] == "2026-11-03T00:00:00Z"
    assert TL.build_month(db, "2026-09", NOW)["balances"] is None


def test_hash_changes_when_entry_added_and_is_stable():
    db = make()
    a = TL.build_month(db, "2026-10", NOW)["hash"]
    assert TL.build_month(db, "2026-10", NOW + 5)["hash"] == a            # generated_at is not hashed
    AE.add_entry(db, {"kind": "cost", "date": "2026-10-20", "amount_cents": 100, "category": "other", "machine_id": "m4"}, 3)
    assert TL.build_month(db, "2026-10", NOW)["hash"] != a


def test_response_codes_and_months_listing():
    db = make()
    code, ctype, body = TL.tally_response(db, "/v1/tally/monthly?month=2026-10", NOW)
    assert code == 200 and json.loads(body)["month"] == "2026-10" and json.loads(body)["timezone"] == TZ
    for bad in ("/v1/tally/monthly", "/v1/tally/monthly?month=2026-13", "/v1/tally/monthly?month=2026-1", "/v1/tally/monthly?month=abcd-ef",
                "/v1/tally/monthly?month=1999-01", "/v1/tally/monthly?month=2026-10&x=1", "/v1/tally/months?x=1"):
        assert TL.tally_response(db, bad, NOW)[0] == 400, bad
    code, _, body = TL.tally_response(db, "/v1/tally/months", NOW)
    months = json.loads(body)["months"]
    assert [m["month"] for m in months] == ["2026-10", "2026-11"] and all(set(m) == {"month", "final", "hash"} for m in months)
    assert months[0]["hash"] == TL.build_month(db, "2026-10", NOW)["hash"]


def test_apportion_sums_exactly():
    assert TL.apportion(10, {"a": 1, "b": 1, "c": 1}) == {"a": 4, "b": 3, "c": 3}
    assert TL.apportion(None, {"a": 1}) == {"a": None}
    assert TL.apportion(5, {"a": 0, "b": 0}) == {"a": 5, "b": 0}


def test_no_secrets_in_output():
    body = TL.tally_response(make(), "/v1/tally/monthly?month=2026-10", NOW)[2].decode().lower()
    assert "token" not in body and "api_key" not in body
