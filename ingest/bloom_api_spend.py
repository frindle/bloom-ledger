"""Darkbloom API spend: the account's own paid usage (plex-automation's paid layer), pulled every 15 minutes.

GET https://api.darkbloom.dev/v1/payments/usage (Bearer, the account key saved in Settings) answers the newest usage rows first:
request_id, model, prompt_tokens, completion_tokens, cost_micro_usd, timestamp. There is no date filter and no pagination, so each
pass reads the response from the newest row down and stops at the first row already stored (INSERT OR IGNORE keeps the table
duplicate-free anyway). Only rows at or after the `api_spend_from_ts` setting (epoch seconds; env BLOOM_API_SPEND_FROM_TS when the
setting is unset) are kept; with neither set nothing is ingested.

Classification: every usage row is the owner's personal use, so it is an OWNER DRAW from the Darkbloom balance, never an expense
against Darkbloom income. A card top-up is an OWNER CONTRIBUTION the owner enters by hand (entry kind "contribution"), because the
API shows no deposit history.

The key goes only to the allowlisted Darkbloom hosts (bloom_accounting_live.http_get_json) and is never logged or stored here. A 401/403
(the key may lack payments scope) is skipped and shown in the key status as state "no_scope"."""
import datetime as dt
import json
import os
import re

import bloom_accounting_config as CF
import bloom_accounting_live as LV

USAGE_URL = "https://api.darkbloom.dev/v1/payments/usage"
EVERY_S = 900
MAX_ROWS = 100000
ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
TOL_MICRO = 50000   # reconcile slack: 5 cents of rounding and timing between a balance snapshot and the rows
TOL_PCT = 2


def create_table(db):
    db.execute("CREATE TABLE IF NOT EXISTS api_spend (request_id TEXT PRIMARY KEY, ts INTEGER NOT NULL, model TEXT,"
               " prompt_tokens INTEGER, completion_tokens INTEGER, cost_micro_usd INTEGER NOT NULL)")
    db.execute("CREATE INDEX IF NOT EXISTS api_spend_ts ON api_spend (ts)")
    db.commit()


def status_path(root):
    return os.path.join(LV.keys_dir(root), "darkbloom_api_spend.status.json")


def _set_status(root, now, state, http=0, added=0):
    LV._write_private(status_path(root), json.dumps({"checked_at": now, "state": state, "http": http, "added": added}))


def from_ts(db):
    v = CF.effective_settings(db, "9999-12-31")["values"].get("api_spend_from_ts")
    if v is None:
        v = os.environ.get("BLOOM_API_SPEND_FROM_TS")
    try:
        return None if v in (None, "") or isinstance(v, bool) else int(float(v))
    except (TypeError, ValueError):
        return None


def parse_ts(v):
    """Epoch seconds from an epoch number (seconds or milliseconds) or an ISO-8601 string; None when unusable."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        v = float(v)
        return int(v / 1000) if v > 1e11 else int(v)
    if isinstance(v, str) and v.strip():
        s = v.strip()
        if re.fullmatch(r"\d+(\.\d+)?", s):
            return parse_ts(float(s))
        try:
            d = dt.datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith("Z") else s)
        except ValueError:
            return None
        return int((d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).timestamp())
    return None


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def rows_of(j):
    """The usage rows (a list of dicts, newest first) from a response that is a list or an object holding one."""
    if isinstance(j, dict):
        for k in ("usage", "data", "rows", "items", "results"):
            if isinstance(j.get(k), list):
                j = j[k]
                break
    return [r for r in j if isinstance(r, dict)] if isinstance(j, list) else None


def clean(r):
    """One response row -> (request_id, ts, model, prompt_tokens, completion_tokens, cost_micro_usd) or None."""
    rid, ts, cost = r.get("request_id"), parse_ts(r.get("timestamp", r.get("ts"))), r.get("cost_micro_usd")
    if not isinstance(rid, str) or not ID_RE.match(rid) or ts is None or isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
        return None
    model = r.get("model")
    return (rid, ts, model[:200] if isinstance(model, str) else None, _int(r.get("prompt_tokens")), _int(r.get("completion_tokens")), int(cost))


def ingest(db, root, now, lock=None, get=LV.http_get_json):
    """One pass. Returns {"state", "http", "added"}; the same is saved for the key status. The HTTP call runs before `lock`
    (the caller's DB lock) is taken. state: ok, no_key, no_start, no_scope (401/403), unreachable, bad_response."""
    key = LV.read_key(root)
    start = from_ts(db)
    if not key:
        return {"state": "no_key", "http": 0, "added": 0}
    if start is None:
        res = {"state": "no_start", "http": 0, "added": 0}
        _set_status(root, now, **res)
        return res
    code, j = get(USAGE_URL, key)
    if code in (401, 403):
        res = {"state": "no_scope", "http": code, "added": 0}
    elif code != 200:
        res = {"state": "unreachable", "http": code, "added": 0}
    else:
        rows = rows_of(j)
        if rows is None:
            res = {"state": "bad_response", "http": code, "added": 0}
        else:
            res = {"state": "ok", "http": code, "added": _store(db, rows[:MAX_ROWS], start, lock)}
    _set_status(root, now, **res)
    return res


def _store(db, rows, start, lock):
    class _Null:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    added = 0
    with (lock or _Null()):
        create_table(db)
        for r in rows:
            c = clean(r)
            if c is None:
                continue
            if c[1] < start:
                break   # newest first: everything after this is older too
            if db.execute("SELECT 1 FROM api_spend WHERE request_id = ?", (c[0],)).fetchone():
                break   # reached rows already stored
            cur = db.execute("INSERT OR IGNORE INTO api_spend (request_id, ts, model, prompt_tokens, completion_tokens, cost_micro_usd)"
                             " VALUES (?, ?, ?, ?, ?, ?)", c)
            added += cur.rowcount
        db.commit()
    return added


def month_totals(db, lo, hi):
    """(requests, prompt_tokens, completion_tokens, cost_micro_usd) of the rows with lo <= ts < hi."""
    create_table(db)
    n, p, c, m = db.execute("SELECT COUNT(*), COALESCE(SUM(prompt_tokens), 0), COALESCE(SUM(completion_tokens), 0),"
                            " COALESCE(SUM(cost_micro_usd), 0) FROM api_spend WHERE ts >= ? AND ts < ?", (lo, hi)).fetchone()
    return n, p, c, m


def _near(a, b, scale):
    return abs(a - b) <= max(TOL_MICRO, scale * TOL_PCT // 100)


def reconcile(db, lo, hi, contribution_micro=0):
    """What explains the change in the Darkbloom balance over [lo, hi): "earnings_pay" (withdrawable moved by earnings minus the
    draws), "credit_pays" (withdrawable moved by earnings alone while credits fell by the draws), or "not_enough_data".
    Credits are available minus withdrawable. Needs two different balance snapshots in or just before the range, and some draws."""
    create_table(db)
    import bloom_power_lib as P

    def snap(sql, arg):
        row = db.execute(sql, (P.utc_iso(arg),)).fetchone()
        return None if row is None or row[1] is None or row[2] is None else row
    first = (snap("SELECT at, available_micro_usd, withdrawable_micro_usd FROM account_totals WHERE at <= ? ORDER BY at DESC LIMIT 1", lo)
             or snap("SELECT at, available_micro_usd, withdrawable_micro_usd FROM account_totals WHERE at >= ? ORDER BY at LIMIT 1", lo))
    last = snap("SELECT at, available_micro_usd, withdrawable_micro_usd FROM account_totals WHERE at <= ? ORDER BY at DESC LIMIT 1", hi)
    earn = db.execute("SELECT COALESCE(SUM(micro_usd), 0) FROM earnings WHERE ts >= ? AND ts < ?", (lo, hi)).fetchone()[0]
    draw = month_totals(db, lo, hi)[3]
    out = {"supported": "not_enough_data", "earnings_cents": earn // 10000, "draws_cents": draw // 10000,
           "contribution_cents": contribution_micro // 10000, "withdrawable_change_cents": None, "credits_change_cents": None}
    if first is None or last is None or first[0] == last[0] or draw == 0:
        out["why"] = "needs two balance snapshots in the range and some API spend"
        return out
    dw = last[2] - first[2]
    dc = (last[1] - last[2]) - (first[1] - first[2])
    out["withdrawable_change_cents"], out["credits_change_cents"] = dw // 10000, dc // 10000
    scale = max(abs(earn), draw)
    a = _near(dw, earn - draw, scale) and _near(dc, contribution_micro, scale)
    b = _near(dw, earn, scale) and _near(dc, contribution_micro - draw, scale)
    if a and not b:
        out["supported"] = "earnings_pay"
    elif b and not a:
        out["supported"] = "credit_pays"
    else:
        out["why"] = "the balance change fits both explanations" if a and b else "the balance change fits neither explanation"
    return out
