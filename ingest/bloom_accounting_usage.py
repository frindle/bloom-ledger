"""Accounting usage: business share of machine time from per-minute power rows.

ASSUMPTION (flagged): a minute counts as paid Darkbloom work when power was measured, tokens were served or a Sandbox job ran, and no other work ran. Percentages are integer basis points (10000 = 100%). Not tax advice."""


def is_paid_minute(row):
    """True when the minute row shows paid work: power_ok truthy, tokens_delta > 0 or a Darkbloom Sandbox job running
    (sandbox_jobs > 0, absent counts as 0), and no other_work."""
    sandbox = (row["sandbox_jobs"] if "sandbox_jobs" in row.keys() else 0) or 0
    return bool(row["power_ok"]) and ((row["tokens_delta"] or 0) > 0 or sandbox > 0) and not row["other_work"]


def m4_business_bp(rows):
    """Owned-Mac business share in basis points: paid minutes * 10000 // minutes with measured power; 0 when none."""
    total = sum(1 for r in rows if r["power_ok"])
    paid = sum(1 for r in rows if is_paid_minute(r))
    return paid * 10000 // total if total else 0


def personal_minutes(windows, timestamps):
    """Count timestamps (epoch seconds) inside any personal window; windows are half-open (start, end) pairs."""
    return sum(1 for t in timestamps if any(s <= t < e for s, e in windows))


def m5_business_bp(total_minutes, personal_minutes):
    if total_minutes <= 0:
        return 0
    personal = max(0, min(personal_minutes, total_minutes))
    return (total_minutes - personal) * 10000 // total_minutes


def personal_token_share(total_tokens, personal_minutes, total_minutes):
    if total_minutes <= 0:
        return 0
    personal = max(0, min(personal_minutes, total_minutes))
    return total_tokens * personal // total_minutes
