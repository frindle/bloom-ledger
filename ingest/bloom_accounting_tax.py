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



def entry_amounts_micro(entries, start, end, bp):
    """Calculate receipt, expense and electricity amounts in micro-USD for entries in [start, end].

    Only entries with start <= e["date"] <= end (inclusive YYYY-MM-DD strings) count.
    Entries are dicts with kind, date, amount_cents, category.
    - kind "receipt" (any category): amount_cents * 10000 into receipts_micro.
    - kind "cost":
      - category "electricity": amount_cents * 10000 into electricity_micro only (metered power
        already counts that electricity, so it is NOT expensed).
      - category "internet": amount_cents * (bp or 0) // 10000 * 10000 into expensed_micro
        (business share in basis points, rounded down to the cent; bp None counts as 0).
      - category "hardware": skipped (it is depreciated elsewhere).
      - any other category (software, supplies, other): amount_cents * 10000 into expensed_micro.
    - All three keys are always present (0 when nothing counts).
    """
    receipts_micro = 0
    expensed_micro = 0
    electricity_micro = 0

    for e in entries:
        if e["date"] < start or e["date"] > end:
            continue
        kind = e["kind"]
        cat = e.get("category", "")
        cents = e["amount_cents"]
        if kind == "receipt":
            receipts_micro += cents * 10000
        elif kind == "cost":
            pct = e.get("business_pct")
            if pct is None:
                pct = 100
            if cat == "electricity":
                electricity_micro += cents * 10000
            elif cat == "internet":
                share = bp or 0
                expensed_micro += cents * pct // 100 * share // 10000 * 10000
            elif cat != "hardware":
                expensed_micro += cents * pct // 100 * 10000

    return {"receipts_micro": receipts_micro, "expensed_micro": expensed_micro,
            "electricity_micro": electricity_micro}



def pre_tracking_micro(db, start, end, from_date):
    """Return micro-USD of earnings before per-job tracking began.

    Rules:
    - Return 0 when from_date is falsy or not start <= from_date <= end
      (inclusive YYYY-MM-DD strings).
    - Read the FIRST account total: SELECT at, total_micro_usd FROM
      account_totals ORDER BY at LIMIT 1. Return 0 when there is no row
      or its total is None.
    - Convert at (an ISO time like '2026-10-13T19:13:39Z') to a UTC
      epoch integer: int(dt.datetime.fromisoformat(at.replace('Z', '+00:00')).timestamp()).
    - seen = SELECT COALESCE(SUM(micro_usd), 0) FROM earnings WHERE ts <= ?
      with that epoch (earnings at exactly at count as seen).
    - Return max(total - seen, 0).
    """
    if not from_date:
        return 0
    # Validate: start <= from_date <= end (inclusive YYYY-MM-DD)
    if from_date < start or from_date > end:
        return 0
    row = db.execute(
        'SELECT at, total_micro_usd FROM account_totals ORDER BY at LIMIT 1'
    ).fetchone()
    if row is None or row[1] is None:
        return 0
    at_str, total = row[0], row[1]
    epoch = int(dt.datetime.fromisoformat(at_str.replace('Z', '+00:00')).timestamp())
    seen = db.execute(
        'SELECT COALESCE(SUM(micro_usd), 0) FROM earnings WHERE ts <= ?',
        (epoch,)
    ).fetchone()[0]
    return max(total - seen, 0)

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


def month_rows(year, shares, fixed, extras=None):
    """The 12 monthly business-view rows of `year` from month_shares output and per-month fixed costs.

    fixed is {"YYYY-MM": {"depreciation_business_cents", "lease_business_cents"}} (cents at business share, None = input not set).
    extras is {"YYYY-MM": {"other_income_micro", "entries_business_micro"}} (default 0 when key missing).
    Row keys: month, income_micro, other_income_micro, bp, power_business_micro (power * bp // 10000), depreciation_business_micro,
    lease_business_micro (cents * 10000), entries_business_micro, expenses_micro (power + dep + lease + ent, None when any is None)
    and net_micro (income + other - expenses, None when expenses is None)."""
    rows = []
    for key in sorted(shares):
        s, f = shares[key], fixed.get(key, {})
        x = (extras or {}).get(key, {})
        other = x.get("other_income_micro", 0)
        ent = x.get("entries_business_micro", 0)
        power = None if s["power_micro"] is None else s["power_micro"] * (s["bp"] or 0) // 10000
        dep, lease = (None if f.get(k) is None else f[k] * 10000 for k in ("depreciation_business_cents", "lease_business_cents"))
        parts = (power, dep, lease, ent)
        exp = None if None in parts else sum(parts)
        rows.append({"month": key, "income_micro": s["income_micro"], "other_income_micro": other, "bp": s["bp"],
                     "power_business_micro": power, "depreciation_business_micro": dep, "lease_business_micro": lease,
                     "entries_business_micro": ent, "expenses_micro": exp,
                     "net_micro": None if exp is None else s["income_micro"] + other - exp})
    return rows


def tax_totals(rows):
    """Year totals over month_rows output: the sum of each *_micro column; a column is None when any month's value is None.

    Keys: income_micro, other_income_micro, power_business_micro, depreciation_business_micro, lease_business_micro,
    entries_business_micro, expenses_micro, net_micro."""
    out = {}
    for k in ("income_micro", "other_income_micro", "power_business_micro", "depreciation_business_micro", "lease_business_micro",
              "entries_business_micro", "expenses_micro", "net_micro"):
        vals = [r[k] for r in rows]
        out[k] = None if None in vals else sum(vals)
    return out


def fixed_by_month(settings, entries, year, shares, through=None):
    """Per-month fixed costs at business share, {"YYYY-MM": {"depreciation_business_cents", "lease_business_cents"}} for each key of `shares`.

    The share for a month is its shares[key]["bp"] (0 when None). When settings["machines"] is a non-empty list the machine records are
    summed with FX.machine_fixed_cents (None if any machine gives None); otherwise the legacy settings are used (FX.owned_depreciation_cents
    and FX.lease_cents, then DP.business_cents; None when those inputs are not set). `entries` are the live ledger entries.
    When `through` is not None and a month's computed end satisfies start <= through < end, the end is truncated to through."""
    out = {}
    for key in sorted(shares):
        y, m = int(key[:4]), int(key[5:])
        start = "%s-01" % key
        end = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()
        if through is not None and start <= through < end:
            end = through
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

    Business share is paid minutes only. Voided entries are excluded. Pre-tracking pay is computed by pre_tracking_micro
    for the month holding m4_in_service_date, receipts are other income, entries follow entry_amounts_micro,
    fixed costs stop at today.
    Keys: year, view, months (month_rows), totals (tax_totals), disclaimer."""
    settings = CF.effective_settings(db, "%d-12-31" % year)["values"]
    start, end = "%d-01-01" % year, "%d-12-31" % year
    shares = month_shares(year, RP.day_rows(db, settings["local_timezone"], start, end, None, settings))
    entries = AE.current_entries(db)
    fixed = fixed_by_month(settings, entries, year, shares, dt.date.today().isoformat())
    extras = {}
    for key, s in shares.items():
        a, b = key + "-01", key + "-31"
        s["income_micro"] += pre_tracking_micro(db, a, b, settings.get("m4_in_service_date"))
        amt = entry_amounts_micro(entries, a, b, s["bp"])
        extras[key] = {"other_income_micro": amt["receipts_micro"], "entries_business_micro": amt["expensed_micro"]}
    months = month_rows(year, shares, fixed, extras)
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
    """Answer GET `path` for the tax routes with (status, content_type, body_bytes).

    /tax[?year=YYYY] -> the HTML page (year defaults to the current year); /v1/accounting/tax?year=YYYY&view=business|hobby&format=json|csv
    -> the report (view defaults to business, format to json). A year outside 2000..2100, a non-integer year or an unknown view/format
    -> 400 JSON {"error": "bad request"}; any other path -> 404 JSON {"error": "not found"}."""
    parts = urllib.parse.urlsplit(path)
    q = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
    bad = (400, "application/json", b'{"error": "bad request"}')
    if parts.path not in ("/tax", "/v1/accounting/tax"):
        return (404, "application/json", b'{"error": "not found"}')
    try:
        year = int(q["year"]) if "year" in q else dt.date.today().year
    except ValueError:
        return bad
    if not 2000 <= year <= 2100 or q.get("view", "business") not in ("business", "hobby") or q.get("format", "json") not in ("json", "csv"):
        return bad
    if parts.path == "/tax":
        return (200, "text/html; charset=utf-8", TP.tax_page(year).encode())
    report = build_tax(db, year, q.get("view", "business"))
    if q.get("format") == "csv":
        return (200, "text/csv; charset=utf-8", tax_csv(report).encode())
    return (200, "application/json", json.dumps(report, sort_keys=True).encode())
