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
    """Year totals over month_rows output: the sum of each *_micro column; a column is None when any month's value is None.

    Keys: income_micro, power_business_micro, depreciation_business_micro, lease_business_micro, expenses_micro, net_micro."""
    out = {}
    for k in ("income_micro", "power_business_micro", "depreciation_business_micro", "lease_business_micro", "expenses_micro", "net_micro"):
        vals = [r[k] for r in rows]
        out[k] = None if None in vals else sum(vals)
    return out


def fixed_by_month(settings, entries, year, shares):
    out = {}
    machines = settings.get("machines")
    links = settings.get("entry_machine_links")
    for key in sorted(shares):
        bp = shares[key].get("bp") or 0
        y, m = key.split("-")
        start = "%s-%02d-01" % (y, int(m))
        mm = int(m)
        if mm == 12:
            nxt = "%s-01-01" % str(int(y) + 1)
        else:
            nxt = "%s-%02d-01" % (y, mm + 1)
        end = (dt.date.fromisoformat(nxt) - dt.timedelta(days=1)).isoformat()
        if machines:
            dep_total = lease_total = None
            for mch in machines:
                r = FX.machine_fixed_cents(mch, entries, links, start, end, bp)
                d = r.get("depreciation_business_cents")
                l = r.get("lease_business_cents")
                if dep_total is None and d is not None:
                    dep_total = 0
                if dep_total is not None and d is not None:
                    dep_total += d
                elif d is None:
                    dep_total = None
                if lease_total is None and l is not None:
                    lease_total = 0
                if lease_total is not None and l is not None:
                    lease_total += l
                elif l is None:
                    lease_total = None
            out[key] = {"depreciation_business_cents": dep_total, "lease_business_cents": lease_total}
        else:
            dep = FX.owned_depreciation_cents(settings, entries, start, end)
            lease = FX.lease_cents(settings, start, end)
            dep_biz = DP.business_cents(dep, bp) if dep is not None else None
            lease_biz = DP.business_cents(lease, bp) if lease is not None else None
            out[key] = {"depreciation_business_cents": dep_biz, "lease_business_cents": lease_biz}
    return out
