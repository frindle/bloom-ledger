"""Machine configuration for the ledger: validated records for owned and leased machines, kept append-only (retired, never deleted).

Bookkeeping, not tax advice. Money is integer cents; dates are YYYY-MM-DD."""
import datetime as dt
import re

OWNERSHIP = ("owned", "leased")
BUSINESS_MODES = ("auto_paid_hours", "leased_100", "personal_windows")
DEP_METHODS = ("straight_line", "section179", "macrs5")
ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")


def _date_ok(v):
    raise NotImplementedError("_date_ok")


def _cents_ok(v):
    raise NotImplementedError("_cents_ok")


def validate_machine(m):
    raise NotImplementedError("validate_machine")
