"""Write-off rules: what counts as business use and how power, depreciation and the lease are deducted.

One accounting setting, "write_off", holds the rules (effective-dated like every other setting). Anything missing or
malformed falls back to DEFAULTS, which reproduce the ledger's original behaviour: only paid Darkbloom and Sandbox
minutes are business use, deductible power is the metered cost of those minutes, the business share is measured, and a
lease is all business. Bookkeeping choices, not tax advice: the person filing confirms them with their tax preparer."""

DEFAULTS = {
    "count": {"darkbloom": True, "sandbox": True, "own": False, "idle": False},
    "power": "work_minutes",
    "share": "measured",
    "fixed_pct": None,
    "lease_pct": 100,
}
POWER_METHODS = ("work_minutes", "share_of_total", "all", "none")
SHARE_MODES = ("measured", "fixed")
STREAM_KEY = {"gpu": "darkbloom", "sandbox": "sandbox", "other": "own", "idle": "idle"}
ONLINE_STATES = ("idle", "serving")


def _pct(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100


def rules(settings):
    """Normalised write-off rules from effective settings values (a dict, or None for the defaults)."""
    raw = (settings or {}).get("write_off")
    raw = raw if isinstance(raw, dict) else {}
    count = dict(DEFAULTS["count"])
    if isinstance(raw.get("count"), dict):
        count.update({k: v for k, v in raw["count"].items() if k in count and isinstance(v, bool)})
    out = {"count": count}
    out["power"] = raw.get("power") if raw.get("power") in POWER_METHODS else DEFAULTS["power"]
    out["share"] = raw.get("share") if raw.get("share") in SHARE_MODES else DEFAULTS["share"]
    out["fixed_pct"] = raw.get("fixed_pct") if _pct(raw.get("fixed_pct")) else None
    if out["share"] == "fixed" and out["fixed_pct"] is None:
        out["share"] = "measured"
    out["lease_pct"] = raw.get("lease_pct") if _pct(raw.get("lease_pct")) else DEFAULTS["lease_pct"]
    return out


def validate(value):
    """[] when `value` is a usable write_off setting, else a list of plain-language problems."""
    if not isinstance(value, dict):
        return ["write_off must be an object"]
    errs = []
    unknown = set(value) - set(DEFAULTS)
    if unknown:
        errs.append("unknown write_off fields: " + ", ".join(sorted(unknown)))
    c = value.get("count", {})
    if not isinstance(c, dict) or any(k not in DEFAULTS["count"] or not isinstance(v, bool) for k, v in c.items()):
        errs.append("count must map darkbloom, sandbox, own and idle to true or false")
    if "power" in value and value["power"] not in POWER_METHODS:
        errs.append("power must be one of " + ", ".join(POWER_METHODS))
    if "share" in value and value["share"] not in SHARE_MODES:
        errs.append("share must be measured or fixed")
    if value.get("share") == "fixed" and not _pct(value.get("fixed_pct")):
        errs.append("a fixed share needs fixed_pct between 0 and 100")
    for k in ("fixed_pct", "lease_pct"):
        if value.get(k) is not None and not _pct(value[k]):
            errs.append(k + " must be between 0 and 100")
    return errs


def minute_counts(r, stream, state):
    """True when a measured minute of `stream` counts as business use under rules `r`. Idle minutes count only while
    Darkbloom was online (idle or serving) and idle is switched on; gaps never count."""
    key = STREAM_KEY.get(stream)
    if key is None or not r["count"][key]:
        return False
    return key != "idle" or (state or "") in ONLINE_STATES


def share_bp(r, measured_bp):
    """Business share in basis points: the fixed percent when set, else the measured share (None stays None)."""
    if r["share"] == "fixed":
        return int(round(r["fixed_pct"] * 100))
    return measured_bp


def power_business_micro(r, t):
    """Deductible power (micro-USD) from day_rows totals `t`; None when power cost is not known."""
    cost = t.get("cost_micro")
    if cost is None:
        return None
    if r["power"] == "none":
        return 0
    if r["power"] == "all":
        return cost
    if r["power"] == "share_of_total":
        bp = share_bp(r, t.get("business_bp"))
        return cost * (bp or 0) // 10000
    return t.get("business_cost_micro", (t.get("gpu_cost_micro") or 0) + (t.get("sandbox_cost_micro") or 0))


def lease_business_cents(r, lease_cents):
    """The deductible part of a lease amount in cents (None stays None)."""
    if lease_cents is None:
        return None
    return lease_cents * int(round(r["lease_pct"] * 100)) // 10000


def describe(r):
    """One plain sentence per rule, for reports and the tax packet."""
    names = {"darkbloom": "Darkbloom inference", "sandbox": "Sandbox jobs", "own": "your own local work",
             "idle": "idle time while Darkbloom is online"}
    on = [names[k] for k in ("darkbloom", "sandbox", "own", "idle") if r["count"][k]]
    power = {"work_minutes": "the metered cost of business-use minutes", "share_of_total": "the whole power cost at the business share",
             "all": "all metered power", "none": "no power"}[r["power"]]
    share = "fixed at %s%%" % r["fixed_pct"] if r["share"] == "fixed" else "measured from logged minutes"
    return ["Business use counts: " + (", ".join(on) if on else "nothing") + ".",
            "Deductible power: " + power + ".",
            "Business share (used for depreciation): " + share + ".",
            "Lease deducted at %s%%." % r["lease_pct"]]
