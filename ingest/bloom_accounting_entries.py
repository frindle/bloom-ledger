"""Accounting entries: validated cost and receipt entries kept in an append-only sqlite table (never edited, only voided).

Not tax advice. Money is integer cents; dates are YYYY-MM-DD."""
import datetime as dt


KINDS = ("cost", "receipt")
CATEGORIES = ("hardware", "software", "internet", "electricity", "supplies", "other")


def validate_entry(e):
    if not isinstance(e, dict):
        return "not an object"
    if e.get("kind") not in KINDS:
        return "bad kind"
    d = e.get("date")
    if not isinstance(d, str) or len(d) != 10:
        return "bad date"
    try:
        dt.date.fromisoformat(d)
    except (ValueError, TypeError):
        return "bad date"
    a = e.get("amount_cents")
    if not isinstance(a, int) or isinstance(a, bool) or a <= 0:
        return "bad amount"
    if e.get("category") not in CATEGORIES:
        return "bad category"
    mid = e.get("machine_id")
    if mid is not None and (not isinstance(mid, str) or not mid):
        return "bad machine_id"
    note = e.get("note")
    if note is not None and not isinstance(note, str):
        return "bad note"
    return None
