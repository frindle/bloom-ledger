"""Machine configuration for the ledger: validated records for owned and leased machines, kept append-only (retired, never deleted).

Bookkeeping, not tax advice. Money is integer cents; dates are YYYY-MM-DD."""
import datetime as dt
import re

OWNERSHIP = ("owned", "leased")
BUSINESS_MODES = ("auto_paid_hours", "leased_100", "personal_windows")
DEP_METHODS = ("straight_line", "section179", "macrs5")
ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")


def _date_ok(v):
    if not isinstance(v, str) or len(v) != 10:
        return False
    try:
        dt.date.fromisoformat(v)
        return True
    except ValueError:
        return False


def validate_machine(m):
    if not isinstance(m, dict):
        return {"form": "not an object"}
    errors = {}

    # id: must match ID_RE fully
    rid = m.get("id")
    if not isinstance(rid, str) or not ID_RE.fullmatch(rid):
        errors["id"] = "id must be a lowercase alphanumerics with hyphens or underscores"

    # display_name: non-blank string, max 60 chars
    dn = m.get("display_name")
    if not isinstance(dn, str) or not dn.strip():
        errors["display_name"] = "display_name must be a non-blank string"
    elif len(dn) > 60:
        errors["display_name"] = "display_name must be 60 characters or fewer"

    # processor: non-blank string, max 60 chars
    proc = m.get("processor")
    if not isinstance(proc, str) or not proc.strip():
        errors["processor"] = "processor must be a non-blank string"
    elif len(proc) > 60:
        errors["processor"] = "processor must be 60 characters or fewer"

    # ownership: must be in OWNERSHIP
    own = m.get("ownership")
    if own not in OWNERSHIP:
        errors["ownership"] = "ownership must be one of: owned, leased"

    # in_service: valid date string
    ins = m.get("in_service")
    if not _date_ok(ins):
        errors["in_service"] = "in_service must be a valid date like YYYY-MM-DD"

    # business_mode: must be in BUSINESS_MODES
    bm = m.get("business_mode")
    if bm not in BUSINESS_MODES:
        errors["business_mode"] = "business_mode must be one of the allowed modes"

    # watts: optional (None ok); when present must be int/float, not bool, 0 < watts <= 5000
    w = m.get("watts")
    if w is not None:
        if isinstance(w, bool) or not isinstance(w, (int, float)):
            errors["watts"] = "watts must be a number"
        elif w <= 0 or w > 5000:
            errors["watts"] = "watts must be between 1 and 5000"

    return errors
