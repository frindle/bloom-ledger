"""Accounting usage: business share of machine time from per-minute power rows.

ASSUMPTION (flagged): a minute counts as paid Darkbloom work when power was measured, tokens were served and no other work ran. Percentages are integer basis points (10000 = 100%). Not tax advice."""


def is_paid_minute(row):
    if not row["power_ok"]:
        return False
    if (row["tokens_delta"] or 0) <= 0:
        return False
    if row.get("other_work") is not None and row["other_work"]:
        return False
    return True


def m4_business_bp(rows):
    total = sum(1 for r in rows if r["power_ok"])
    paid = sum(1 for r in rows if is_paid_minute(r))
    if total == 0:
        return 0
    return paid * 10000 // total
