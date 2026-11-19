"""Monthly invoice: lines by earnings kind, costs, usage and the net, from synthetic rows. Fake numbers."""
import json

import bloom_invoice as INV
import bloom_accounting_tally as TL
from test_tally_monthly import NOW, make, utc

LINES = {"job": 1_250_000, "sandbox": 480_000, "base": 270_001}


def seeded():
    db = make()
    n = 100
    for kind, micro in LINES.items():
        n += 1
        db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, completion_tokens, source_machine) VALUES (?,?,?,?,?,?)",
                   ("x%d" % n, utc(2026, 11, 12, 18, 0), micro, kind, 40 if kind == "job" else 0, "m4"))
    db.commit()
    return db


def test_lines_add_up_to_the_tally_gross():
    db = seeded()
    inv, tally = INV.build_invoice(db, "2026-11", NOW), TL.build_month(db, "2026-11", NOW)
    assert inv["gross_cents"] == tally["totals"]["earnings_cents"] > 0
    assert sum(l["amount_cents"] for l in inv["lines"]) == inv["gross_cents"]
    by = {l["key"]: l for l in inv["lines"]}
    assert by["sandbox"]["count"] == 1 and by["base_reward"]["count"] == 1
    assert by["inference"]["amount_cents"] > by["sandbox"]["amount_cents"] > by["base_reward"]["amount_cents"] - 1
    assert inv["invoice_id"] == "BL-2026-11" and inv["issue_date"] == "2026-12-01" and inv["currency"] == "USD"


def test_net_is_gross_plus_other_income_minus_known_costs():
    db = seeded()
    inv = INV.build_invoice(db, "2026-11", NOW)
    costs = sum(c["amount_cents"] for c in inv["costs"] if c["amount_cents"] is not None)
    assert inv["other_income_cents"] == 501 and costs > 0
    assert inv["net_cents"] == inv["gross_cents"] + inv["other_income_cents"] - costs


def test_usage_and_honest_gaps():
    db = seeded()
    inv = INV.build_invoice(db, "2026-11", NOW)
    assert inv["usage"]["tokens"] == 5 * 3 * 2 + 40   # the fixture's six job rows of 5 tokens in November, plus 40
    assert inv["usage"]["jobs"] == 9 and inv["usage"]["vcpu_seconds"] is None
    assert inv["fees_cents"] is None and "fee" in inv["fees_note"]


def test_same_data_same_hash_and_change_changes_it():
    db = seeded()
    a, b = INV.build_invoice(db, "2026-11", NOW), INV.build_invoice(db, "2026-11", NOW + 5)
    assert a["hash"] == b["hash"] and a["generated_at"] != b["generated_at"]
    db.execute("UPDATE earnings SET micro_usd = micro_usd + 20000 WHERE ledger_id = 'x101'")
    db.commit()
    assert INV.build_invoice(db, "2026-11", NOW)["hash"] != a["hash"]


def test_months_index_matches_each_invoice():
    db = seeded()
    idx = INV.build_invoice_months(db, NOW)["months"]
    assert [m["month"] for m in idx] == ["2026-10", "2026-11"]
    for m in idx:
        assert m["hash"] == INV.build_invoice(db, m["month"], NOW)["hash"]


def test_response_validation():
    db = seeded()
    code, ctype, body = INV.invoice_response(db, "/v1/invoice/monthly?month=2026-11", NOW)
    assert code == 200 and ctype == "application/json" and json.loads(body)["month"] == "2026-11"
    for bad in ("/v1/invoice/monthly", "/v1/invoice/monthly?month=2026-13", "/v1/invoice/monthly?month=2026-11&x=1", "/v1/invoice/months?x=1"):
        assert INV.invoice_response(db, bad, NOW)[0] == 400
    assert INV.invoice_response(db, "/v1/invoice/other", NOW)[0] == 404
