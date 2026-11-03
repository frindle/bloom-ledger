"""Frozen test: bloom_accounting_tax.entry_amounts_micro (which ledger entries count, and how much). Fake numbers."""
import bloom_accounting_tax as T


def fn(name):
    f = getattr(T, name, None)
    assert callable(f), "bloom_accounting_tax." + name + " is missing"
    return f


def e(kind, cat, cents, date="2026-10-10"):
    return {"id": 1, "kind": kind, "date": date, "amount_cents": cents, "category": cat, "machine_id": None, "note": None}


E = [e("receipt", "other", 1500, "2026-10-01"), e("cost", "software", 1200), e("cost", "supplies", 300), e("cost", "other", 100, "2026-10-31"),
     e("cost", "internet", 6000), e("cost", "electricity", 4000), e("cost", "hardware", 99999), e("cost", "software", 777, "2026-11-01")]


def test_expensed_receipts_and_electricity_in_range():
    assert fn("entry_amounts_micro")(E, "2026-10-01", "2026-10-31", 2500) == {
        "receipts_micro": 15000000, "expensed_micro": (1200 + 300 + 100) * 10000 + 1500 * 10000, "electricity_micro": 40000000}


def test_internet_share_rounds_down_to_the_cent_and_none_share_is_zero():
    f = fn("entry_amounts_micro")
    assert f([e("cost", "internet", 999)], "2026-10-01", "2026-10-31", 3333)["expensed_micro"] == 332 * 10000
    assert f(E, "2026-10-01", "2026-10-31", None)["expensed_micro"] == 1600 * 10000


def test_electricity_bill_is_not_added_on_top_of_metered_power():
    sh = T.month_shares(2026, [{"date": "2026-10-10", "earned_micro": 0, "minutes": 10, "paid_minutes": 10, "cost_micro": 40000000}])["2026-10"]
    amt = fn("entry_amounts_micro")([e("cost", "electricity", 4000)], "2026-10-01", "2026-10-31", sh["bp"])
    assert amt["expensed_micro"] == 0 and amt["electricity_micro"] == sh["power_micro"]


def test_out_of_range_and_empty():
    f = fn("entry_amounts_micro")
    assert f(E, "2026-11-01", "2026-11-30", 10000) == {"receipts_micro": 0, "expensed_micro": 7770000, "electricity_micro": 0}
    assert f([], "2026-10-01", "2026-10-31", 10000) == {"receipts_micro": 0, "expensed_micro": 0, "electricity_micro": 0}
