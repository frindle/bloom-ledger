"""Fixed machine costs in integer cents for a date range: lease expense and depreciation.

Accrual is cumulative by day so periods add up exactly. Bookkeeping estimates, not tax advice."""
import datetime as dt
import bloom_accounting_depr as DP


def _cum_lease(monthly, months, start, day):
    days = (day - start).days + 1
    if days <= 0:
        return 0
    total = monthly * months
    return min(total, monthly * 12 * days // 365)


def lease_cents(settings, start, end):
    """Lease expense (cents) for the inclusive range start..end, or None when the lease amount, term or start date is not set."""
    monthly, months, begin = (settings.get(k) for k in ("m5_lease_monthly_cents", "m5_lease_months", "m5_lease_start"))
    if monthly is None or months is None or begin is None:
        return None
    b, s, e = (dt.date.fromisoformat(x) for x in (begin, start, end))
    return _cum_lease(monthly, months, b, e) - _cum_lease(monthly, months, b, s - dt.timedelta(days=1))

def entry_business_cents(e):
    """The business-use part of one entry in cents: amount_cents * business_pct // 100 (business_pct missing or None = 100)."""
    pct = e.get("business_pct")
    return e["amount_cents"] * (100 if pct is None else pct) // 100


def depreciation_basis_cents(entries, machine=None):
    """Sum hardware costs from cost entries; None when nothing matches."""
    total = 0
    found = False
    for e in entries:
        if e.get("kind") == "cost" and e.get("category") == "hardware":
            if machine is not None and e.get("machine_id") != machine:
                continue
            total += entry_business_cents(e)
            found = True
    return total if found else None


def owned_depreciation_cents(settings, entries, start, end, machine=None):
    """Depreciation (cents) for owned hardware under `settings` for the range start..end.

    Each hardware entry is its own asset placed in service on the later of its date
    and the setting.
    """
    basis = depreciation_basis_cents(entries, machine)
    in_service = settings.get("m4_in_service_date")
    if basis is None or not in_service:
        return None
    method = settings.get("dep_method")
    life = settings.get("dep_life_months")
    total = 0
    for e in entries:
        if e.get("kind") != "cost" or e.get("category") != "hardware":
            continue
        if machine is not None and e.get("machine_id") != machine:
            continue
        placed = max(e.get("date") or in_service, in_service)
        total += DP.depreciation_cents(method, entry_business_cents(e), placed, life, start, end)
    return total


def machine_basis_cents(machine, entries, links=None):
    """Depreciable basis (cents) of one owned machine record: its live hardware cost entries, else its purchase_cents, else None.

    An entry belongs to the machine when links maps str(entry id) to the machine id, or (no link) its machine_id is the machine id."""
    links = links or {}
    total, found = 0, False
    for e in entries:
        if e.get("kind") == "cost" and e.get("category") == "hardware" and links.get(str(e["id"]), e.get("machine_id")) == machine["id"]:
            total += entry_business_cents(e)
            found = True
    return total if found else machine.get("purchase_cents")


def machine_fixed_cents(machine, entries, links, start, end, default_bp=None):
    """Fixed costs (cents) of one machine record for the inclusive range start..end, gross and at business share.

    Returns {"depreciation_cents", "depreciation_business_cents", "lease_cents", "lease_business_cents"}; depreciation is None
    when an owned machine has no basis. default_bp (basis points, None = 10000) is the business share for years the machine
    record gives no business_use_bp. default_bp applies to owned depreciation only; a lease is 100% business unless the record's
    business_use_bp lists that year."""
    bp = 10000 if default_bp is None else default_bp
    dep = dep_biz = None
    lease = 0
    if machine["ownership"] == "owned":
        basis = machine_basis_cents(machine, entries, links)
        if basis is not None:
            asset = {"basis_cents": basis, "placed_in_service": machine["in_service"], "method": machine.get("depreciation_method", "macrs5"),
                     **{k: machine[k] for k in ("class", "convention", "section179_cents", "bonus_bp", "business_use_bp") if k in machine}}
            dep = DP.asset_depreciation_cents(asset, start, end)
            dep_biz = DP.asset_business_cents(asset, start, end, bp)
        lease_biz = 0
    else:
        b, s, e = (dt.date.fromisoformat(x) for x in (machine["lease_start"], start, end))
        months = machine.get("lease_months") or 1200
        lease = _cum_lease(machine["lease_monthly_cents"], months, b, e) - _cum_lease(machine["lease_monthly_cents"], months, b, s - dt.timedelta(days=1))
        # A leased machine is assumed all business. Documented personal use is recorded on the machine record as
        # business_use_bp[year] (e.g. 9500 after logging 5% personal use) and lowers that year's deductible lease.
        lease_biz = DP.business_cents(lease, (machine.get("business_use_bp") or {}).get(start[:4], 10000))
        dep = dep_biz = 0
    return {"depreciation_cents": dep, "depreciation_business_cents": dep_biz, "lease_cents": lease, "lease_business_cents": lease_biz}
