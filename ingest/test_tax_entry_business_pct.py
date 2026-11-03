"""Frozen test: entry_amounts_micro counts only the business-use percent of each expensed entry. Fake numbers."""
import bloom_accounting_tax as T


def e(cat, cents, pct, kind="cost"):
    d = {"id": 1, "kind": kind, "date": "2026-10-10", "amount_cents": cents, "category": cat, "machine_id": None, "note": None}
    if pct != "absent":
        d["business_pct"] = pct
    return d


def amounts(entries, bp=10000):
    return T.entry_amounts_micro(entries, "2026-10-01", "2026-10-31", bp)


def test_expensed_entries_count_their_business_percent():
    assert amounts([e("software", 1000, 40)])["expensed_micro"] == 400 * 10000
    assert amounts([e("supplies", 999, 33)])["expensed_micro"] == 329 * 10000
    assert amounts([e("other", 500, 100), e("software", 200, None), e("supplies", 300, "absent")])["expensed_micro"] == 1000 * 10000


def test_internet_takes_business_percent_then_the_minute_share():
    assert amounts([e("internet", 6000, 50)], 2500)["expensed_micro"] == 750 * 10000
    assert amounts([e("internet", 999, 70)], 3333)["expensed_micro"] == 699 * 3333 // 10000 * 10000

    others_ignore_business_percent()


def others_ignore_business_percent():
    """Receipts, electricity bills and hardware ignore business_pct."""
    r = amounts([e("other", 1500, 10, kind="receipt"), e("electricity", 4000, 10), e("hardware", 9999, 10)])
    assert r == {"receipts_micro": 15000000, "expensed_micro": 0, "electricity_micro": 40000000}
