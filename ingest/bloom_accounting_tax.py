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
    """The 12 monthly business-view rows of `year` from month_shares output and per-month fixed costs.

    fixed is {"YYYY-MM": {"depreciation_business_cents", "lease_business_cents"}} (cents at business share, None = input not set).
    Row keys: month, income_micro, bp, power_business_micro (power * bp // 10000), depreciation_business_micro, lease_business_micro
    (cents * 10000), expenses_micro and net_micro (income - expenses). Any None input makes that part, expenses_micro and net_micro None."""
    rows = []
    for key in sorted(shares):
        s, f = shares[key], fixed.get(key, {})
        power = None if s["power_micro"] is None else s["power_micro"] * (s["bp"] or 0) // 10000
        dep, lease = (None if f.get(k) is None else f[k] * 10000 for k in ("depreciation_business_cents", "lease_business_cents"))
        parts = (power, dep, lease)
        exp = None if None in parts else sum(parts)
        rows.append({"month": key, "income_micro": s["income_micro"], "bp": s["bp"], "power_business_micro": power,
                     "depreciation_business_micro": dep, "lease_business_micro": lease, "expenses_micro": exp,
                     "net_micro": None if exp is None else s["income_micro"] - exp})
    return rows


def tax_totals(rows):
    keys = ("income_micro", "power_business_micro", "depreciation_business_micro", "lease_business_micro", "expenses_micro", "net_micro")
    out = {}
    for k in keys:
        vals = [r[k] for r in rows]
        out[k] = 0 if not vals else (sum(v for v in vals) if None not in vals else None)
    return out
