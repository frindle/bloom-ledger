"""Monthly "mock invoice" for the resell-tracker: one month of Darkbloom earnings as an invoice document.

GET /v1/invoice/monthly?month=YYYY-MM and GET /v1/invoice/months (see invoice_response). Read-only, no secrets in it.
Built on the monthly tally (bloom_accounting_tally), so the totals are the tally's: the same day boundary, rounding and
write-off rules. This module adds what the tally does not split: the earnings by kind (inference, sandbox, base reward) and the
usage behind them (tokens, jobs, paid minutes). Money is integer cents.

What the numbers mean (Penn, 2026-11-19):
- Net = gross - Darkbloom fees - power - Mac lease (plus any other income and hand-entered expenses). No depreciation line: the
  lease already covers the Mac.
- Darkbloom takes 10% of Sandbox cost; inference and base reward carry no fee. The earnings feed (and so the earnings table)
  stores what Darkbloom PAID, i.e. cost minus the fee: sandbox payouts come in round tenths of cost (2250 for a 2500 job) and the
  rows add up to the account's lifetime total, which is a payout balance. So gross = payout + fee, where fee = sandbox payout / 9,
  and net does not subtract the fee a second time beyond turning the payout back into gross. The feed has no per-row fee, so the
  10% is applied to the month's Sandbox payout.
- usage.vcpu_seconds is null: the earnings feed carries amount, model, job id and completion tokens, no vCPU seconds.
Bookkeeping, not tax advice."""
import datetime as dt
import hashlib
import json
import re
import urllib.parse

import bloom_accounting_config as CF
import bloom_accounting_report as RP
import bloom_accounting_tally as TL
import bloom_power_lib as P

SCHEMA_VERSION = 2
LINE_KINDS = (("job", "inference", "Inference"), ("sandbox", "sandbox", "Sandbox jobs"), ("base", "base_reward", "Base reward"))
FEES_NOTE = "Darkbloom keeps 10% of Sandbox cost (no fee on inference); computed from the payouts the ledger holds."
COST_COLUMNS = (("power_cost_cents", "Metered power"), ("lease_cents", "Equipment lease"),
                ("entries_deductible_cents", "Purchases and other expenses"))   # no depreciation: the lease covers the Mac


def build_invoice(db, month, now, today=None):
    """The invoice dict for `month` (YYYY-MM); ValueError for a malformed month."""
    tally = TL.build_month(db, month, now, today)
    start, end = TL.month_bounds(month)
    settings = CF.effective_settings(db, end)["values"]
    tz = settings["local_timezone"]
    lo, hi = RP.ts_bounds(tz, start, end)
    kinds = {k: {"micro": 0, "count": 0, "tokens": 0} for k, _, _ in LINE_KINDS}
    for kind, n, micro, tok in db.execute("SELECT kind, COUNT(*), COALESCE(SUM(micro_usd), 0), COALESCE(SUM(completion_tokens), 0)"
                                          " FROM earnings WHERE ts >= ? AND ts < ? GROUP BY kind", (lo, hi)):
        k = kinds.get(kind) or kinds["job"]
        k["micro"] += micro
        k["count"] += n
        k["tokens"] += tok
    payout = tally["totals"]["earnings_cents"] or 0
    fees = tally["totals"]["fees_cents"] or 0
    gross = payout + fees   # what the work cost the buyers; Darkbloom paid out `payout` after taking `fees`
    weights = {k: v["micro"] for k, v in kinds.items()}
    weights["sandbox"] += fees * 10000 if kinds["sandbox"]["micro"] else 0   # the fee belongs to the Sandbox line
    rest = gross * 10000 - sum(weights.values())
    if rest > 0:
        weights["other"] = rest   # pay the day rows do not carry (pay from before tracking began), so the lines always add up
    cents = TL.apportion(gross, weights)
    lines = [{"key": key, "label": label, "amount_cents": cents[k], "count": kinds[k]["count"], "tokens": kinds[k]["tokens"]}
             for k, key, label in LINE_KINDS]
    if "other" in cents:
        lines.append({"key": "other", "label": "Other earlier pay", "amount_cents": cents["other"], "count": 0, "tokens": 0})
    t = RP.totals(RP.day_rows(db, tz, start, end, None, None))
    usage = {"tokens": sum(v["tokens"] for v in kinds.values()), "jobs": sum(v["count"] for v in kinds.values()),
             "inference_minutes": t["gpu_minutes"], "sandbox_minutes": t["sandbox_minutes"], "vcpu_seconds": None}
    totals = tally["totals"]
    costs = [{"key": c.replace("_cents", ""), "label": label, "amount_cents": totals[c]} for c, label in COST_COLUMNS]
    other_income = totals["other_income_cents"] or 0
    known = [c["amount_cents"] for c in costs if c["amount_cents"] is not None]
    net = gross + other_income - fees - sum(known)
    body = {"month": month, "invoice_id": "BL-" + month, "issue_date": TL.month_bounds(_next(month))[0], "currency": "USD",
            "gross_cents": gross, "fees_cents": fees, "fees_note": FEES_NOTE, "other_income_cents": other_income,
            "lines": lines, "costs": costs, "costs_unknown": [c["key"] for c in costs if c["amount_cents"] is None],
            "net_cents": net, "usage": usage, "timezone": tz, "machine_count": sum(1 for m in tally["machines"] if not m["shared"])}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"schema_version": SCHEMA_VERSION, "final": tally["final"], "hash": digest, "generated_at": P.utc_iso(now), **body}


def _next(month):
    y, m = int(month[:4]), int(month[5:])
    return "%04d-%02d" % (y + (m == 12), m % 12 + 1)


def build_invoice_months(db, now, today=None):
    """{"generated_at", "months": [{"month", "final", "hash"}]} for every month with data, oldest first (hash is the invoice's)."""
    rows = []
    for key in TL.months_with_data(db):
        inv = build_invoice(db, key, now, today)
        rows.append({"month": key, "final": inv["final"], "hash": inv["hash"]})
    return {"generated_at": P.utc_iso(now), "months": rows}


def invoice_response(db, path, now):
    """Answer GET `path` with (status, content_type, body_bytes): /v1/invoice/monthly?month=YYYY-MM, /v1/invoice/months.
    Bad or missing month, a year outside 2000..2100 or any unexpected query -> 400; any other path -> 404."""
    parts = urllib.parse.urlsplit(path)
    q = urllib.parse.parse_qs(parts.query)

    def ok(obj):
        return (200, "application/json", json.dumps(obj, sort_keys=True).encode())
    bad = (400, "application/json", b'{"error": "bad request"}')
    if parts.path == "/v1/invoice/months":
        return bad if q else ok(build_invoice_months(db, now))
    if parts.path != "/v1/invoice/monthly":
        return (404, "application/json", b'{"error": "not found"}')
    month = (q.get("month") or [""])[0]
    if set(q) != {"month"} or len(q["month"]) != 1 or not TL.MONTH_RE.match(month) or not 2000 <= int(month[:4]) <= 2100:
        return bad
    return ok(build_invoice(db, month, now))
