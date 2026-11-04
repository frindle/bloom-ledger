"""Machine configuration for the ledger: validated records for owned and leased machines, kept append-only (retired, never deleted).

Bookkeeping, not tax advice. Money is integer cents; dates are YYYY-MM-DD."""
import datetime as dt
import re

OWNERSHIP = ("owned", "leased")
BUSINESS_MODES = ("auto_paid_hours", "leased_100", "personal_windows")
DEP_METHODS = ("macrs5", "macrs_150db", "ads", "straight_line", "section179", "de_minimis", "manual")
CLASSES = ("3-year", "5-year", "7-year")
CONVENTIONS = ("half_year", "mid_quarter")
ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")


def _date_ok(v):
    if not isinstance(v, str) or len(v) != 10:
        return False
    try:
        dt.date.fromisoformat(v)
        return True
    except ValueError:
        return False



def _cents_ok(v):
    if not isinstance(v, int) or isinstance(v, bool):
        return False
    return v > 0


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


    # owned: purchase_cents must pass _cents_ok; depreciation_method must be in DEP_METHODS
    # leased: lease_monthly_cents must pass _cents_ok; lease_start must pass _date_ok
    if own == "owned":
        if not _cents_ok(m.get("purchase_cents")):
            errors["purchase_cents"] = "purchase_cents must be a positive integer"
        if m.get("depreciation_method") not in DEP_METHODS:
            errors["depreciation_method"] = "depreciation_method must be one of the allowed methods"
    elif own == "leased":
        if not _cents_ok(m.get("lease_monthly_cents")):
            errors["lease_monthly_cents"] = "lease_monthly_cents must be a positive integer"
        if not _date_ok(m.get("lease_start")):
            errors["lease_start"] = "lease_start must be a valid date like YYYY-MM-DD"

    cl = m.get("class")
    if cl is not None and cl not in CLASSES:
        errors["class"] = "class must be one of: " + ", ".join(CLASSES)
    conv = m.get("convention")
    if conv is not None and conv not in CONVENTIONS:
        errors["convention"] = "convention must be half_year or mid_quarter"

    # section179_cents and bonus_bp: when not None, must be int (bool excluded) >= 0;
    #   bonus_bp must also be <= 10000
    s179 = m.get("section179_cents")
    if s179 is not None:
        if isinstance(s179, bool) or not isinstance(s179, int):
            errors["section179_cents"] = "section179_cents must be a non-negative integer"
        elif s179 < 0:
            errors["section179_cents"] = "section179_cents must be a non-negative integer"

    bbp = m.get("bonus_bp")
    if bbp is not None:
        if isinstance(bbp, bool) or not isinstance(bbp, int):
            errors["bonus_bp"] = "bonus_bp must be an integer between 0 and 10000"
        elif bbp < 0 or bbp > 10000:
            errors["bonus_bp"] = "bonus_bp must be an integer between 0 and 10000"

    # business_use_bp: when not None, must be a dict whose every key matches r"\\d{4}"
    #   and every value is int (bool excluded) from 0 to 10000 inclusive
    bubp = m.get("business_use_bp")
    if bubp is not None:
        bad_key = False
        bad_val = False
        if isinstance(bubp, dict):
            for k, v in bubp.items():
                if not re.fullmatch(r"\d{4}", str(k)):
                    bad_key = True
                if isinstance(v, bool) or not isinstance(v, int):
                    bad_val = True
                elif v < 0 or v > 10000:
                    bad_val = True
        else:
            bad_key = True
            bad_val = True
        if bad_key or bad_val:
            errors["business_use_bp"] = "business_use_bp must be a dict of 4-digit years to integers 0-10000"

    # lease_months: when not None, must be int (bool excluded) > 0
    lm = m.get("lease_months")
    if lm is not None:
        if isinstance(lm, bool) or not isinstance(lm, int):
            errors["lease_months"] = "lease_months must be a positive integer"
        elif lm <= 0:
            errors["lease_months"] = "lease_months must be a positive integer"

    # watts: optional (None ok); when present must be int/float, not bool, 0 < watts <= 5000
    w = m.get("watts")
    if w is not None:
        if isinstance(w, bool) or not isinstance(w, (int, float)):
            errors["watts"] = "watts must be a number"
        elif w <= 0 or w > 5000:
            errors["watts"] = "watts must be between 1 and 5000"

    _depreciation_options(m, errors, ins if _date_ok(ins) else None)
    return errors


def _nonneg_int(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _year_cents_ok(v):
    return isinstance(v, dict) and all(re.fullmatch(r"\d{4}", str(k)) and _nonneg_int(x) for k, x in v.items())


def _depreciation_options(m, errors, ins):
    """Checks for the optional depreciation fields: life, salvage, disposal, manual schedule and the state book."""
    lm = m.get("life_months")
    if lm is not None and not (_nonneg_int(lm) and 0 < lm <= 600):
        errors["life_months"] = "life_months must be a whole number of months from 1 to 600"
    sv = m.get("salvage_cents")
    if sv is not None:
        if not _nonneg_int(sv):
            errors["salvage_cents"] = "salvage_cents must be a non-negative integer"
        elif _cents_ok(m.get("purchase_cents")) and sv > m["purchase_cents"]:
            errors["salvage_cents"] = "salvage_cents cannot be more than the purchase price"
    d = m.get("disposed_on")
    if d is not None:
        if not _date_ok(d):
            errors["disposed_on"] = "disposed_on must be a valid date like YYYY-MM-DD"
        elif ins and d < ins:
            errors["disposed_on"] = "disposed_on cannot be before in_service"
    dp = m.get("disposal_price_cents")
    if dp is not None and not _nonneg_int(dp):
        errors["disposal_price_cents"] = "disposal_price_cents must be a non-negative integer"
    ms = m.get("manual_schedule_cents")
    if ms is not None and not _year_cents_ok(ms):
        errors["manual_schedule_cents"] = "manual_schedule_cents must map 4-digit years to non-negative integer cents"
    if m.get("depreciation_method") == "manual" and not ms:
        errors["manual_schedule_cents"] = "a manual schedule needs at least one year"
    if m.get("depreciation_method") == "de_minimis" and _cents_ok(m.get("purchase_cents")) and m["purchase_cents"] > 250000:
        errors["depreciation_method"] = "the de minimis safe harbor is limited to $2,500 per item"
    st = m.get("state")
    if st is not None:
        bad = []
        if not isinstance(st, dict):
            bad.append("must be an object")
        else:
            unknown = sorted(set(st) - {"name", "method", "convention", "class", "section179_cents", "bonus_bp", "life_months",
                                         "salvage_cents", "manual_schedule_cents"})
            if unknown:
                bad.append("unknown fields " + ", ".join(unknown))
            if "name" in st and not (isinstance(st["name"], str) and 0 < len(st["name"].strip()) <= 40):
                bad.append("name must be 1-40 characters")
            if "method" in st and st["method"] not in DEP_METHODS:
                bad.append("method must be one of the allowed methods")
            if "convention" in st and st["convention"] not in CONVENTIONS:
                bad.append("convention must be half_year or mid_quarter")
            if "class" in st and st["class"] not in CLASSES:
                bad.append("class must be one of " + ", ".join(CLASSES))
            for k in ("section179_cents", "salvage_cents"):
                if k in st and not _nonneg_int(st[k]):
                    bad.append(k + " must be a non-negative integer")
            if "bonus_bp" in st and not (_nonneg_int(st["bonus_bp"]) and st["bonus_bp"] <= 10000):
                bad.append("bonus_bp must be 0-10000")
            if "life_months" in st and not (_nonneg_int(st["life_months"]) and 0 < st["life_months"] <= 600):
                bad.append("life_months must be 1-600")
            if "manual_schedule_cents" in st and not _year_cents_ok(st["manual_schedule_cents"]):
                bad.append("manual_schedule_cents must map years to cents")
            if st.get("method") == "manual" and not st.get("manual_schedule_cents"):
                bad.append("a manual state schedule needs at least one year")
        if bad:
            errors["state"] = "state: " + "; ".join(bad)
