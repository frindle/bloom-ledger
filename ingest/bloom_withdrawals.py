"""Darkbloom withdrawal requests, found from the balance snapshots. Record only: nothing here calls a Darkbloom endpoint.

Darkbloom's public API has no payout list, and withdrawals are made by hand in its Billing page. What the ledger does hold is
the account_totals snapshots (available and withdrawable, written by the archive pass that also fetches the earnings). Between two
consecutive snapshots the withdrawable balance moves by earnings minus the API draws it paid for, so a drop the rows do not
explain is money that left the account: a withdrawal request.

  unexplained = expected change in withdrawable - actual change      (a withdrawal when more than the tolerance)
  expected    = earnings in (a, b] - API draws in (a, b]             (the draws were paid from withdrawable)
              = earnings in (a, b]                                   (when credits fell by the draws: credits paid them)
Credits are available minus withdrawable; a withdrawal leaves them alone, so a credits drop of about the draws says the draws
came out of credits. Tolerance: the larger of 5 cents and 2% of the earnings plus draws in the window. Two withdrawals between
the same two snapshots read as one. A card top-up in the same window hides the credits signal, so the amount can read low;
the tracker takes a hand-entered request for that. Amounts are whole cents (micro-USD // 10000).

Withdrawals are made by hand, several a month, and each ends sent or failed-and-refunded. A failed one comes back to the withdrawable
balance, so a window where withdrawable ROSE by more than expected (same tolerance) is matched to the most recent earlier request that
is not yet refunded and whose amount is within the larger of 5 cents and 2% of the rise (closest amount wins, then the latest); that
request is marked refunded at the snapshot that showed the rise. An unmatched rise is ignored. A retry is a new request (new key).
Limit: a refund and a retry between the same two snapshots net to one smaller drop, so they read as a single smaller request.

GET /v1/withdrawals -> {"generated_at", "withdrawals": [{"key", "requested_at", "since", "amount_cents", "status", "refunded_at"}]},
oldest first. `requested_at` is the snapshot that first showed the drop (the request was made between `since` and it). `status` is
"requested" or "refunded"; `refunded_at` is the snapshot time that showed the rise, or null. No query is allowed."""
import hashlib
import json
import urllib.parse

import bloom_api_spend as SP
import bloom_power_lib as P

TOL_MICRO = SP.TOL_MICRO
TOL_PCT = SP.TOL_PCT


def _sum(db, table, col, lo, hi):
    return db.execute("SELECT COALESCE(SUM(%s), 0) FROM %s WHERE ts > ? AND ts <= ?" % (col, table), (lo, hi)).fetchone()[0]


def detect(db):
    """Every withdrawal the snapshots show, oldest first, as dicts (key, requested_at, since, amount_cents, status, refunded_at)."""
    SP.create_table(db)
    snaps = [r for r in db.execute("SELECT at, available_micro_usd, withdrawable_micro_usd FROM account_totals"
                                   " WHERE available_micro_usd IS NOT NULL AND withdrawable_micro_usd IS NOT NULL")]
    snaps.sort(key=lambda r: P.parse_iso(r[0]))
    out = []
    for a, b in zip(snaps, snaps[1:]):
        lo, hi = int(P.parse_iso(a[0]).timestamp()), int(P.parse_iso(b[0]).timestamp())
        earn = _sum(db, "earnings", "micro_usd", lo, hi)
        draw = _sum(db, "api_spend", "cost_micro_usd", lo, hi)
        dw = b[2] - a[2]
        dc = (b[1] - b[2]) - (a[1] - a[2])
        expected = earn if draw and dc <= -draw + max(TOL_MICRO, draw * TOL_PCT // 100) else earn - draw
        unexplained = expected - dw
        tol = max(TOL_MICRO, (earn + draw) * TOL_PCT // 100)
        if unexplained > tol and unexplained // 10000 > 0:
            key = "w-" + hashlib.sha256(P.utc_iso(hi).encode()).hexdigest()[:16]
            out.append({"key": key, "requested_at": P.utc_iso(hi), "since": P.utc_iso(lo), "amount_cents": unexplained // 10000,
                        "status": "requested", "refunded_at": None})
        elif -unexplained > tol and -unexplained // 10000 > 0:
            rise = -unexplained // 10000
            near = max(5, rise * 2 // 100)
            cands = [w for w in out if w["status"] == "requested" and abs(w["amount_cents"] - rise) <= near]
            if cands:
                best = min(cands, key=lambda w: (abs(w["amount_cents"] - rise), -out.index(w)))
                best["status"] = "refunded"
                best["refunded_at"] = P.utc_iso(hi)
    return out


def withdrawals_response(db, path, now):
    """Answer GET `path` with (status, content_type, body_bytes): /v1/withdrawals. Any query -> 400; any other path -> 404."""
    parts = urllib.parse.urlsplit(path)
    if parts.path != "/v1/withdrawals":
        return (404, "application/json", b'{"error": "not found"}')
    if parts.query:
        return (400, "application/json", b'{"error": "bad request"}')
    body = {"generated_at": P.utc_iso(now), "withdrawals": detect(db)}
    return (200, "application/json", json.dumps(body, sort_keys=True).encode())
