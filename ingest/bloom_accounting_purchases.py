"""Purchases for the ledger: a purchase has line items, each allocated to machines; kept append-only (voided, never deleted).

Bookkeeping, not tax advice. Money is integer cents; dates are YYYY-MM-DD."""
import datetime as dt

TREATMENTS = ("expense", "depreciate")
MAX_ITEMS = 50


def _date_ok(v):
    if not isinstance(v, str) or len(v) != 10:
        return False
    try:
        dt.date.fromisoformat(v)
        return True
    except ValueError:
        return False


def validate_purchase(p):
    errors = {}
    if not isinstance(p, dict):
        return {"form": "not an object"}
    # merchant: non-blank string, at most 80 chars
    m = p.get("merchant")
    if not isinstance(m, str) or not m.strip():
        errors["merchant"] = "must be a non-blank string"
    elif len(m) > 80:
        errors["merchant"] = "must be at most 80 characters"
    # order_number: optional, when given must be string of at most 60 chars
    on = p.get("order_number")
    if on is not None:
        if not isinstance(on, str) or len(on) > 60:
            errors["order_number"] = "must be a string of at most 60 characters"
    # purchase_date: must pass _date_ok
    pd_val = p.get("purchase_date")
    if not _date_ok(pd_val):
        errors["purchase_date"] = "must be a valid date string"
    # note: optional string of at most 500 chars
    note = p.get("note")
    if note is not None:
        if not isinstance(note, str) or len(note) > 500:
            errors["note"] = "must be a string of at most 500 characters"
    # replaces_id: optional, when given must be int (not bool) above 0
    rid = p.get("replaces_id")
    if rid is not None:
        if isinstance(rid, bool) or not isinstance(rid, int) or rid <= 0:
            errors["replaces_id"] = "must be an integer above 0"
    # items: must be a list holding between 1 and MAX_ITEMS entries
    items = p.get("items")
    if not isinstance(items, list) or len(items) < 1 or len(items) > MAX_ITEMS:
        errors["items"] = "must be a list of 1 to %d items" % MAX_ITEMS
    return errors
