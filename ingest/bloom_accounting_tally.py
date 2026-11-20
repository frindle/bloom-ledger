"""Read-only monthly tally: one row per machine (plus a shared row) per local calendar month, for the resell-tracker's books.

GET /v1/tally/monthly?month=YYYY-MM and GET /v1/tally/months (see tally_response). Every figure comes from the same
functions the tax report and packet use (bloom_accounting_tax, _report, _fixed, _writeoff, _entries); this module only splits
a month by machine, rounds to cents and adds the final/hash bookkeeping. Bookkeeping, not tax advice.

Conventions:
- Day boundary: a month is the local calendar month in the settings `local_timezone` effective on the month's last day
  (default America/Los_Angeles), i.e. [first day 00:00, next month 00:00) local time, exactly RP.ts_bounds. Entries use their
  own YYYY-MM-DD date. The write-off rules and every other setting are those effective on the month's last day.
- Rounding: money is integer micro-USD until the end. Each column's month total is converted to cents ONCE, rounded down
  (toward zero, like the packet's money()). The per-machine cents are that total split by largest remainder, so the machine
  rows always add up to the month total, and the month total is floor(tax-report micro / 10000).
- A column is null when the month's total cannot be computed (no rate schedule for power, no basis for depreciation),
  the same as the tax report."""
import datetime as dt
import hashlib
import json
import re
import urllib.parse

import bloom_accounting_config as CF
import bloom_api_spend as SP
import bloom_accounting_entries as AE
import bloom_accounting_report as RP
import bloom_accounting_tax as TX
import bloom_power_lib as P

MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])\Z")
CONVENTION = ("local calendar month in settings local_timezone effective on the month's last day: "
              "[first day 00:00, next month 00:00) local time, the same day boundary as the tax report and packet")
ROUNDING = ("micro-USD to cents once per column per month, rounded down; machine rows split the month total by largest remainder")
COLUMNS = ("earnings_cents", "fees_cents", "other_income_cents", "power_cost_cents", "depreciation_cents", "lease_cents", "entries_deductible_cents")
SHARED = "shared"
SCHEMA_VERSION = 3   # 1 (no field): per-machine rows and balances only. 2: adds schema_version and the account-level block.
#                      3: adds fees_cents (Darkbloom's 10% on Sandbox payouts); earnings_cents stays what Darkbloom paid out (net of that fee)
SANDBOX_FEE_DIVISOR = 9   # a Sandbox row stores the payout, which is 90% of its cost, so the fee is payout / 9 (10% of cost)
ACCOUNT_NOTE = ("Account level, not per machine. draw = the owner's personal use of the Darkbloom balance (API usage rows), "
                "never an expense against Darkbloom income. contribution = money the owner put into the balance by card, entered by hand.")


def apportion(total, weights):
    """Split the integer `total` over the keys of `weights` (non-negative ints) by largest remainder; sums to `total` exactly.
    None total -> every key None. All-zero weights give the whole total to the first key."""
    keys = list(weights)
    if total is None:
        return {k: None for k in keys}
    w = sum(weights.values())
    if not keys:
        return {}
    if w == 0:
        return {k: (total if i == 0 else 0) for i, k in enumerate(keys)}
    q = {k: weights[k] * total // w for k in keys}
    left = total - sum(q.values())
    for k in sorted(keys, key=lambda k: (-(weights[k] * total % w), keys.index(k)))[:left]:
        q[k] += 1
    return q


def month_bounds(month):
    y, m = int(month[:4]), int(month[5:])
    start = dt.date(y, m, 1)
    nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
    return start.isoformat(), (nxt - dt.timedelta(days=1)).isoformat()


def _micro_to_cents(v):
    return None if v is None else v // 10000


def settled_until(db):
    """UTC epoch of the newest earnings poll the ledger holds: the latest account_totals snapshot (written by the same
    archive pass as the earnings it fetched, so it is the server-side form of P.archive_settled_until), or None."""
    row = db.execute("SELECT MAX(at) FROM account_totals").fetchone()
    return None if not row or row[0] is None else int(P.parse_iso(row[0]).timestamp())


def balances(db, end_ts):
    """Latest Darkbloom totals snapshot at or before end_ts as cents, or None."""
    at_max = P.utc_iso(end_ts)
    row = db.execute("SELECT at, available_micro_usd, withdrawable_micro_usd FROM account_totals WHERE at <= ?"
                     " ORDER BY at DESC LIMIT 1", (at_max,)).fetchone()
    if row is None:
        return None
    return {"as_of": row[0], "available_cents": _micro_to_cents(row[1]), "withdrawable_cents": _micro_to_cents(row[2])}


def _machine_ids(db, lo, hi, settings, entry_mids):
    ids = {m["id"] for m in settings.get("machines") or []} | {m for m in entry_mids if m and m != SHARED}
    ids |= {r[0] for r in db.execute("SELECT DISTINCT source_machine FROM earnings WHERE ts >= ? AND ts < ?", (lo, hi)) if r[0]}
    ids |= {r[0] for r in db.execute("SELECT DISTINCT machine_id FROM power_minutes WHERE ts >= ? AND ts < ?", (lo, hi)) if r[0]}
    return sorted(ids)


def _entry_row(e, bp):
    """One entry as the tally shows it. deductible_cents is what TX.entry_amounts_micro expenses for it; effect says why
    it is that: "income" (kind receipt: money received, other income, never a deduction), "capitalized" (hardware, depreciated
    instead), "metered_power" (electricity, already in the metered power cost) or "expense"."""
    amt = TX.entry_amounts_micro([e], e["date"], e["date"], bp)
    if e["kind"] == "contribution":
        effect = "contribution"
    elif e["kind"] == "receipt":
        effect = "income"
    elif e["category"] == "hardware":
        effect = "capitalized"
    elif e["category"] == "electricity":
        effect = "metered_power"
    else:
        effect = "expense"
    pct = e.get("business_pct")
    return {"id": e["id"], "kind": e["kind"], "date": e["date"], "category": e["category"], "vendor": e.get("vendor"),
            "purpose": e.get("purpose"), "business_pct": 100 if pct is None else pct, "amount_cents": e["amount_cents"],
            "deductible_cents": amt["expensed_micro"] // 10000, "effect": effect}


def build_month(db, month, now, today=None):
    """The tally dict for `month` (YYYY-MM); ValueError for a malformed month. `now` is epoch seconds, `today` the
    YYYY-MM-DD the tax report truncates fixed costs at (default the real date)."""
    if not MONTH_RE.match(month):
        raise ValueError("bad month")
    today = today or dt.date.today().isoformat()
    y = int(month[:4])
    start, end = month_bounds(month)
    settings = CF.effective_settings(db, end)["values"]
    tz = settings["local_timezone"]
    lo, hi = RP.ts_bounds(tz, start, end)
    everything = AE.current_entries(db)
    in_month = [e for e in everything if start <= e["date"] <= end]
    contribs = [e for e in in_month if e["kind"] == "contribution"]
    entries = [e for e in in_month if e["kind"] != "contribution"]
    links = settings.get("entry_machine_links") or {}

    def mkey(e):
        return links.get(str(e["id"]), e.get("machine_id")) or SHARED

    ids = _machine_ids(db, lo, hi, settings, [mkey(e) for e in entries])
    # Month totals exactly as the tax report computes them (all machines).
    agg = TX.month_shares(y, RP.day_rows(db, tz, start, end, None, settings), settings)[month]
    pre = TX.pre_tracking_micro(db, start, month + "-31", settings.get("m4_in_service_date"))
    agg["income_micro"] += pre
    fixed = TX.fixed_by_month(settings, everything, y, {month: agg}, today)[month]
    rows_e = [_entry_row(e, agg["bp"]) for e in entries]

    sandbox_w = {r[0] or SHARED: r[1] for r in db.execute("SELECT source_machine, COALESCE(SUM(micro_usd), 0) FROM earnings"
                                                             " WHERE kind = 'sandbox' AND ts >= ? AND ts < ? GROUP BY source_machine", (lo, hi))}
    fee_w = {mid: sandbox_w.get(mid, 0) // SANDBOX_FEE_DIVISOR for mid in ids + [SHARED]}
    earn_w, power_w, dep_w, lease_w = {}, {}, {}, {}
    records = {m["id"]: m for m in settings.get("machines") or []}
    for mid in ids + [SHARED]:
        if mid == SHARED:
            earn_w[mid], power_w[mid] = pre, 0
        else:
            s = TX.month_shares(y, RP.day_rows(db, tz, start, end, mid, settings), settings)[month]
            earn_w[mid], power_w[mid] = s["income_micro"], s["job_power_micro"]
        if records:
            one = TX.fixed_by_month({**settings, "machines": [records[mid]]}, everything, y, {month: agg}, today)[month] if mid in records else {}
            dep_w[mid], lease_w[mid] = one.get("depreciation_business_cents", 0), one.get("lease_business_cents", 0)
        else:  # legacy single-machine settings: fixed costs are not split by machine, so they sit on the shared row
            dep_w[mid] = fixed["depreciation_business_cents"] if mid == SHARED else 0
            lease_w[mid] = fixed["lease_business_cents"] if mid == SHARED else 0

    def split(total, w):
        if total is None or None in w.values():
            return {k: None for k in w}
        return apportion(total, w)

    other_w = {k: 0 for k in earn_w}
    ded_w = {k: 0 for k in earn_w}
    for e, r in zip(entries, rows_e):
        if e["kind"] == "receipt":
            other_w[mkey(e)] += e["amount_cents"]
        ded_w[mkey(e)] += r["deductible_cents"]
    cols = {
        "earnings_cents": split(agg["income_micro"] // 10000, earn_w),
        "fees_cents": apportion(sum(fee_w.values()) // 10000, fee_w),
        "other_income_cents": other_w,
        "power_cost_cents": split(None if agg["job_power_micro"] is None else agg["job_power_micro"] // 10000, power_w),
        "depreciation_cents": split(fixed["depreciation_business_cents"], dep_w),
        "lease_cents": split(fixed["lease_business_cents"], lease_w),
        "entries_deductible_cents": ded_w,
    }
    machines = []
    for mid in ids + [SHARED]:
        row = {"machine_id": None if mid == SHARED else mid, "shared": mid == SHARED}
        row.update({c: cols[c][mid] for c in COLUMNS})
        row["entries"] = [r for e, r in zip(entries, rows_e) if mkey(e) == mid]
        if mid == SHARED or row["entries"] or any(row[c] for c in COLUMNS):
            machines.append(row)
    account = account_block(db, lo, hi, contribs)
    bal = balances(db, hi)
    settled = settled_until(db)
    final = bool(now >= hi and settled is not None and settled >= hi + P.SETTLE_S)
    body = {"machines": machines, "balances": bal, "account": account}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    totals = {c: (None if None in cols[c].values() else sum(cols[c].values())) for c in COLUMNS}
    return {"schema_version": SCHEMA_VERSION, "month": month, "timezone": tz, "day_boundary": CONVENTION, "rounding": ROUNDING,
            "generated_at": P.utc_iso(now), "final": final, "hash": digest, "totals": totals, **body}


def account_block(db, lo, hi, contribs):
    """Account-level money moves of the month [lo, hi): API spend draws (one item) and the hand-entered card top-ups."""
    n, ptok, ctok, micro = SP.month_totals(db, lo, hi)
    items = []
    if n:
        items.append({"effect": "draw", "kind": "api_spend", "amount_cents": micro // 10000, "requests": n,
                      "prompt_tokens": ptok, "completion_tokens": ctok})
    for e in contribs:
        items.append({"effect": "contribution", "kind": "contribution", "id": e["id"], "date": e["date"],
                      "amount_cents": e["amount_cents"], "note": e.get("note")})
    contrib = sum(e["amount_cents"] for e in contribs)
    rec = SP.reconcile(db, lo, hi, contrib * 10000)
    return {"api_spend_draw_cents": micro // 10000, "contribution_cents": contrib, "note": ACCOUNT_NOTE, "items": items,
            "reconcile": rec}


def months_with_data(db):
    """Sorted YYYY-MM months from the first to the last month holding earnings, power minutes, entries or totals snapshots
    that have any of those rows (local months of the newest settings' timezone)."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(CF.effective_settings(db, "9999-12-31")["values"]["local_timezone"])
    seen = set()
    for sql in ("SELECT MIN(ts), MAX(ts) FROM earnings", "SELECT MIN(ts), MAX(ts) FROM power_minutes"):
        a, b = db.execute(sql).fetchone()
        if a is not None:
            seen |= {dt.datetime.fromtimestamp(a, tz).strftime("%Y-%m"), dt.datetime.fromtimestamp(b, tz).strftime("%Y-%m")}
    SP.create_table(db)
    a, b = db.execute("SELECT MIN(ts), MAX(ts) FROM api_spend").fetchone()
    if a is not None:
        seen |= {dt.datetime.fromtimestamp(a, tz).strftime("%Y-%m"), dt.datetime.fromtimestamp(b, tz).strftime("%Y-%m")}
    a, b = db.execute("SELECT MIN(date), MAX(date) FROM acct_entries WHERE voided_at IS NULL").fetchone() if _has_entries(db) else (None, None)
    if a:
        seen |= {a[:7], b[:7]}
    if not seen:
        return []
    y, m = int(min(seen)[:4]), int(min(seen)[5:])
    out, last = [], max(seen)
    while "%04d-%02d" % (y, m) <= last:
        key = "%04d-%02d" % (y, m)
        start, end = month_bounds(key)
        lo, hi = RP.ts_bounds(tz.key, start, end)
        # A month can hold pay with no day rows at all: the pay from before tracking began is booked to the month of the
        # machine's in-service date (pre_tracking_micro), so that month counts as a month with data too.
        has = (TX.pre_tracking_micro(db, start, end, CF.effective_settings(db, end)["values"].get("m4_in_service_date")) > 0
               or db.execute("SELECT 1 FROM earnings WHERE ts >= ? AND ts < ? LIMIT 1", (lo, hi)).fetchone()
               or db.execute("SELECT 1 FROM power_minutes WHERE ts >= ? AND ts < ? LIMIT 1", (lo, hi)).fetchone()
               or db.execute("SELECT 1 FROM api_spend WHERE ts >= ? AND ts < ? LIMIT 1", (lo, hi)).fetchone()
               or (_has_entries(db) and db.execute("SELECT 1 FROM acct_entries WHERE voided_at IS NULL AND date >= ? AND date <= ? LIMIT 1",
                                                   (start, end)).fetchone()))
        if has:
            out.append(key)
        y, m = y + (m == 12), m % 12 + 1
    return out


def _has_entries(db):
    AE.create_entries_table(db)
    return True


def build_months(db, now, today=None):
    """{"generated_at", "months": [{"month", "final", "hash"}]} for every month with data, oldest first."""
    rows = []
    for key in months_with_data(db):
        t = build_month(db, key, now, today)
        rows.append({"month": key, "final": t["final"], "hash": t["hash"]})
    return {"generated_at": P.utc_iso(now), "months": rows}


def tally_response(db, path, now):
    """Answer GET `path` with (status, content_type, body_bytes): /v1/tally/monthly?month=YYYY-MM, /v1/tally/months.
    A missing or malformed month (also a year outside 2000..2100) or any unexpected query -> 400 {"error": "bad request"};
    any other path -> 404."""
    parts = urllib.parse.urlsplit(path)
    q = urllib.parse.parse_qs(parts.query)

    def ok(obj):
        return (200, "application/json", json.dumps(obj, sort_keys=True).encode())
    bad = (400, "application/json", b'{"error": "bad request"}')
    if parts.path == "/v1/tally/months":
        return bad if q else ok(build_months(db, now))
    if parts.path != "/v1/tally/monthly":
        return (404, "application/json", b'{"error": "not found"}')
    month = (q.get("month") or [""])[0]
    if set(q) != {"month"} or len(q["month"]) != 1 or not MONTH_RE.match(month) or not 2000 <= int(month[:4]) <= 2100:
        return bad
    return ok(build_month(db, month, now))
