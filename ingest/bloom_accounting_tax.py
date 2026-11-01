"""Tax-year bookkeeping view of the ledger: monthly income and business-share expenses, for one calendar year.

Bookkeeping, not tax advice. Money is integer cents or integer micro-USD (1e-6 USD) as the field name says; dates are YYYY-MM-DD."""
import csv
import datetime as dt
import io
import json
import urllib.parse

import bloom_accounting_config as CF
import bloom_accounting_depr as DP
import bloom_accounting_entries as AE
import bloom_accounting_fixed as FX
import bloom_accounting_index as AX
import bloom_accounting_report as RP


def month_shares(year, day_rows):
    """Per-month income, metered power cost and paid-minute business share for the 12 months of `year`.

    Returns {"YYYY-MM": {"income_micro", "power_micro" (None when any day's cost is None), "minutes", "paid_minutes", "bp"}} where bp is
    paid_minutes * 10000 // minutes, or None when there are no metered minutes. day_rows are RP.day_rows rows."""
    out = {}
    for m in range(1, 13):
        key = "%04d-%02d" % (year, m)
        rows = [r for r in day_rows if r["date"][:7] == key]
        minutes = sum(r["minutes"] for r in rows)
        paid = sum(r["paid_minutes"] for r in rows)
        costs = [r["cost_micro"] for r in rows]
        out[key] = {"income_micro": sum(r["earned_micro"] for r in rows), "power_micro": None if None in costs else sum(costs),
                    "minutes": minutes, "paid_minutes": paid, "bp": paid * 10000 // minutes if minutes else None}
    return out


def month_rows(year, shares, fixed):
    rows = []
    for key in sorted(shares):
        s = shares[key]
        income_micro = s["income_micro"]
        bp = s.get("bp")
        power_micro = s.get("power_micro")
        power_business_micro = None if power_micro is None else power_micro * (bp or 0) // 10000
        fm = fixed.get(key, {})
        dep_cents = fm.get("depreciation_business_cents")
        lease_cents = fm.get("lease_business_cents")
        depreciation_business_micro = None if dep_cents is None else dep_cents * 10000
        lease_business_micro = None if lease_cents is None else lease_cents * 10000
        parts = [power_business_micro, depreciation_business_micro, lease_business_micro]
        expenses_micro = None if None in parts else sum(parts)
        net_micro = None if expenses_micro is None else income_micro - expenses_micro
        rows.append({"month": key, "income_micro": income_micro, "bp": bp,
                     "power_business_micro": power_business_micro,
                     "depreciation_business_micro": depreciation_business_micro,
                     "lease_business_micro": lease_business_micro,
                     "expenses_micro": expenses_micro, "net_micro": net_micro})
    return rows
