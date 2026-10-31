"""Accounting entries: validated cost and receipt entries kept in an append-only sqlite table (never edited, only voided).

Not tax advice. Money is integer cents; dates are YYYY-MM-DD."""
import datetime as dt


KINDS = ("cost", "receipt")
CATEGORIES = ("hardware", "software", "internet", "electricity", "supplies", "other")


def validate_entry(e):
    raise NotImplementedError("validate_entry")
