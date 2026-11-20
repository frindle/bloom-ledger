"""One number: the invoice net, the tally-derived net and the books' journal agree for every month. Synthetic amounts."""
import bloom_invoice as INV
import bloom_accounting_tally as TL
import bloom_accounting_config as CF
from test_tally_monthly import NOW, make, utc


def tally_net(t):
    """Net the way the tracker's books post a tally month: payout + fees (income) + other income - fees - power - depreciation - lease - expenses."""
    tot = t["totals"]
    g = lambda k: tot[k] or 0
    return (g("earnings_cents") + g("fees_cents")) + g("other_income_cents") - g("fees_cents") - g("power_cost_cents") - g("depreciation_cents") - g("lease_cents") - g("entries_deductible_cents")


def sandbox_db():
    db = make()
    for i, (mach, micro) in enumerate((("m4", 2250), ("m4", 36000), ("m5", 72000), ("m4", 2250))):
        db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, completion_tokens, source_machine) VALUES (?,?,?,?,?,?)",
                   ("s%d" % i, utc(2026, 11, 12, 18, i), micro * 1000, "sandbox", 0, mach))
    db.commit()
    return db


def test_fee_is_ten_percent_of_sandbox_cost_and_inference_has_none():
    db = sandbox_db()
    t = TL.build_month(db, "2026-11", NOW)
    payout = 112_500 * 1000 // 1  # micro: 2250+36000+72000+2250 thousand-fold
    assert t["totals"]["fees_cents"] == (112_500 * 1000 // 9) // 10000
    assert sum(r["fees_cents"] for r in t["machines"]) == t["totals"]["fees_cents"]
    inv = INV.build_invoice(db, "2026-11", NOW)
    assert inv["fees_cents"] == t["totals"]["fees_cents"]
    # gross = payout + fee, and the fee comes off once: net is payout - power - depreciation - lease.
    assert inv["gross_cents"] == t["totals"]["earnings_cents"] + inv["fees_cents"]
    assert sum(l["amount_cents"] for l in inv["lines"]) == inv["gross_cents"]
    oct_inv = INV.build_invoice(db, "2026-10", NOW)
    assert oct_inv["fees_cents"] == 0 and payout > 0


def test_depreciation_is_in_net_and_costs_for_an_owned_machine():
    db = sandbox_db()
    t = TL.build_month(db, "2026-11", NOW)
    dep = t["totals"]["depreciation_cents"]
    assert dep > 0
    inv = INV.build_invoice(db, "2026-11", NOW)
    assert {c["key"]: c["amount_cents"] for c in inv["costs"]}["depreciation"] == dep
    assert inv["net_cents"] == tally_net(t)


def test_invoice_net_equals_tally_net_every_month():
    db = sandbox_db()
    for m in TL.months_with_data(db):
        assert INV.build_invoice(db, m, NOW)["net_cents"] == tally_net(TL.build_month(db, m, NOW)), m


def test_month_with_only_pre_tracking_pay_is_listed():
    db = sandbox_db()
    CF.set_setting(db, "m4_in_service_date", "2026-09-28", "2026-01-01", 5)
    months = TL.months_with_data(db)
    assert "2026-09" in months and months == sorted(months)
    inv = INV.build_invoice(db, "2026-09", NOW)
    assert inv["gross_cents"] > 0
