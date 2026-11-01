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
import bloom_accounting_taxpage as TP


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
    """Per-month fixed costs at business share, {"YYYY-MM": {"depreciation_business_cents", "lease_business_cents"}} for each key of `shares`.

    The share for a month is its shares[key]["bp"] (0 when None). When settings["machines"] is a non-empty list the machine records are
    summed with FX.machine_fixed_cents (None if any machine gives None); otherwise the legacy settings are used (FX.owned_depreciation_cents
    and FX.lease_cents, then DP.business_cents; None when those inputs are not set). `entries` are the live ledger entries."""
    out = {}
    for key in sorted(shares):
        y, m = int(key[:4]), int(key[5:])
        start = "%s-01" % key
        end = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()
        bp = shares[key]["bp"] or 0
        machines = settings.get("machines")
        if machines:
            parts = [FX.machine_fixed_cents(mc, entries, settings.get("entry_machine_links"), start, end, bp) for mc in machines]
            dep, lease = ([p[k] for p in parts] for k in ("depreciation_business_cents", "lease_business_cents"))
            dep, lease = (None if None in v else sum(v) for v in (dep, lease))
        else:
            dep, lease = FX.owned_depreciation_cents(settings, entries, start, end), FX.lease_cents(settings, start, end)
            dep, lease = (None if v is None else DP.business_cents(v, bp) for v in (dep, lease))
        out[key] = {"depreciation_business_cents": dep, "lease_business_cents": lease}
    return out


def apply_view(report, view):
    """Return a copy of a business-view tax report for `view`: "business" unchanged, "hobby" = income only.

    The hobby view keeps only month, income_micro and bp in each month and only income_micro in totals. Sets report["view"].
    ValueError for any other view."""
    if view not in ("business", "hobby"):
        raise ValueError("bad view")
    out = dict(report, view=view)
    if view == "hobby":
        out["months"] = [{k: m[k] for k in ("month", "income_micro", "bp")} for m in report["months"]]
        out["totals"] = {"income_micro": report["totals"]["income_micro"]}
    return out


def build_tax(db, year, view="business"):
    """Tax-year report dict for calendar `year` from the ledger database, shaped for `view` ("business" or "hobby"; ValueError otherwise).

    Business share is paid minutes only. Voided entries are excluded. Keys: year, view, months (month_rows), totals (tax_totals), disclaimer."""
    settings = CF.effective_settings(db, "%d-12-31" % year)["values"]
    start, end = "%d-01-01" % year, "%d-12-31" % year
    shares = month_shares(year, RP.day_rows(db, settings["local_timezone"], start, end, None, settings))
    fixed = fixed_by_month(settings, AE.current_entries(db), year, shares)
    months = month_rows(year, shares, fixed)
    report = {"year": year, "view": "business", "months": months, "totals": tax_totals(months), "disclaimer": "Bookkeeping, not tax advice"}
    return apply_view(report, view)


def tax_csv(report):
    """CSV text (header, one row per month, then a TOTAL row, then the disclaimer line) for a build_tax report.

    Columns are the keys of the first month row, in order, with money columns in whole micro-USD as integers; None is an empty cell."""
    cols = list(report["months"][0]) if report["months"] else ["month", "income_micro"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for m in report["months"]:
        w.writerow(["" if m[c] is None else m[c] for c in cols])
    w.writerow(["TOTAL"] + ["" if report["totals"].get(c, "") is None else report["totals"].get(c, "") for c in cols[1:]])
    w.writerow([report["disclaimer"]])
    return buf.getvalue()


def tax_response(db, path):
    parsed = urllib.parse.urlsplit(path)
    if parsed.path not in ("/tax", "/v1/accounting/tax"):
        return (404, "application/json", b'{"error": "not found"}')
    q = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    try:
        year = int(q["year"][0]) if "year" in q else dt.date.today().year
    except (KeyError, ValueError, IndexError):
        return (400, "application/json", b'{"error": "bad request"}')
    if year < 2000 or year > 2100:
        return (400, "application/json", b'{"error": "bad request"}')
    view = q.get("view", ["business"])[0]
    if view not in ("business", "hobby"):
        return (400, "application/json", b'{"error": "bad request"}')
    fmt = q.get("format", ["json"])[0]
    if fmt not in ("json", "csv"):
        return (400, "application/json", b'{"error": "bad request"}')
    if parsed.path == "/tax":
        return (200, "text/html; charset=utf-8", TP.tax_page(year).encode())
    report = build_tax(db, year, view)
    if fmt == "csv":
        return (200, "text/csv; charset=utf-8", tax_csv(report).encode())
    return (200, "application/json", json.dumps(report, sort_keys=True).encode())
