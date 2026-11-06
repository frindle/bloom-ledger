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
SHARE_MODES = ("measured", "usage", "fixed")
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
        errs.append("share must be measured, usage or fixed")
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


def usage_energy(u):
    """Energy (mJ) one minute's usage puts on {"darkbloom", "sandbox", "own"}, or None when the minute's usage was not
    fully measured. u maps bloom_accounting_index.USAGE_COLUMNS to values (None = not measured). CPU energy is each
    bucket's own kernel counter; GPU energy is the minute's whole-GPU energy split by each bucket's share of all GPU time
    (other users' clients, "sys", take their share and are left out like the rest of the system). When dbk_local is set
    (the operator's own requests reached Darkbloom's local endpoint that minute) Darkbloom's part is the operator's."""
    if not u:
        return None
    keys = ("dbk_cpu_mj", "sbx_cpu_mj", "own_cpu_mj", "dbk_gpu_ms", "sbx_gpu_ms", "own_gpu_ms", "sys_gpu_ms", "gpu_mj")
    if any(u.get(k) is None for k in keys):
        return None
    gms = [u["dbk_gpu_ms"], u["sbx_gpu_ms"], u["own_gpu_ms"], u["sys_gpu_ms"]]
    busy = sum(gms)
    g = [u["gpu_mj"] * v / busy for v in gms[:3]] if busy > 0 else [0.0, 0.0, 0.0]
    e = {"darkbloom": u["dbk_cpu_mj"] + g[0], "sandbox": u["sbx_cpu_mj"] + g[1], "own": u["own_cpu_mj"] + g[2]}
    if u.get("dbk_local"):
        e = {"darkbloom": 0.0, "sandbox": e["sandbox"], "own": e["own"] + e["darkbloom"]}
    return e


def usage_share(r, u):
    """The counted buckets' share (0..1) of one minute's attributable energy (usage_energy), or None when the minute's
    usage was not measured or nothing in it was attributable."""
    e = usage_energy(u)
    total = sum(e.values()) if e else 0
    if total <= 0:
        return None
    return min(1.0, sum(v for k, v in e.items() if r["count"][k]) / total)


def minute_business(r, stream, state, paid, usage=None):
    """Business share (0..1) of one measured minute. Whole minutes (1 when minute_counts, else 0) unless the share is
    "usage" and the minute had paid work (`paid`: tokens served or a Sandbox job running) with its usage measured: then
    it is the counted buckets' share of the minute's energy (usage_share), so the operator's own use beside paid work is
    left out, and paid work beside heavy own work still counts its part."""
    whole = 1.0 if minute_counts(r, stream, state) else 0.0
    if r["share"] != "usage" or not paid:
        return whole
    f = usage_share(r, usage)
    return whole if f is None else f


def share_bp(r, measured_bp):
    """Business share in basis points: the fixed percent when set, else the measured share (whole minutes or usage,
    already in measured_bp; None stays None)."""
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
    share = {"fixed": "fixed at %s%%" % r["fixed_pct"], "measured": "measured from logged minutes",
             "usage": "measured from each paid minute's CPU and GPU use (whole minutes where use was not logged)"}[r["share"]]
    return ["Business use counts: " + (", ".join(on) if on else "nothing") + ".",
            "Deductible power: " + power + ".",
            "Business share (used for depreciation): " + share + ".",
            "Lease deducted at %s%%." % r["lease_pct"]]
