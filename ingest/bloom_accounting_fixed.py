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

def depreciation_basis_cents(entries, machine=None):
    """Sum hardware costs from cost entries; None when nothing matches."""
    total = 0
    found = False
    for e in entries:
        if e.get("kind") == "cost" and e.get("category") == "hardware":
            if machine is not None and e.get("machine_id") != machine:
                continue
            total += e["amount_cents"]
            found = True
    return total if found else None


def owned_depreciation_cents(settings, entries, start, end, machine=None):
    """Depreciation (cents) for owned hardware under `settings` for the range start..end."""
    basis = depreciation_basis_cents(entries, machine)
    in_service = settings.get("m4_in_service_date")
    if basis is None or not in_service:
        return None
    return DP.depreciation_cents(
        settings.get("dep_method"), basis, in_service,
        settings.get("dep_life_months"), start, end
    )


def machine_basis_cents(machine, entries, links=None):
    """Depreciable basis (cents) of one owned machine record: its live hardware cost entries, else its purchase_cents, else None.

    An entry belongs to the machine when links maps str(entry id) to the machine id, or (no link) its machine_id is the machine id."""
    links = links or {}
    total, found = 0, False
    for e in entries:
        if e.get("kind") == "cost" and e.get("category") == "hardware" and links.get(str(e["id"]), e.get("machine_id")) == machine["id"]:
            total += e["amount_cents"]
            found = True
    return total if found else machine.get("purchase_cents")


def machine_fixed_cents(machine, entries, links, start, end, default_bp=None):
    bp = 10000 if default_bp is None else default_bp
    ownership = machine.get("ownership")
    if ownership == "owned":
        basis = machine_basis_cents(machine, entries, links)
        if basis is None:
            return {"depreciation_cents": None, "depreciation_business_cents": None, "lease_cents": 0, "lease_business_cents": 0}
        asset = {"basis_cents": basis, "placed_in_service": machine["in_service"], "method": machine.get("depreciation_method", "macrs5")}
        for k in ("section179_cents", "bonus_bp", "business_use_bp", "class", "convention"):
            if k in machine:
                asset[k] = machine[k]
        dep = DP.asset_depreciation_cents(asset, start, end)
        dep_bus = DP.asset_business_cents(asset, start, end, bp)
        return {"depreciation_cents": dep, "depreciation_business_cents": dep_bus, "lease_cents": 0, "lease_business_cents": 0}
    elif ownership == "leased":
        m = machine["lease_monthly_cents"]
        months = machine.get("lease_months") or 1200
        begin = dt.date.fromisoformat(machine["lease_start"])
        s = dt.date.fromisoformat(start)
        e = dt.date.fromisoformat(end)
        lc = _cum_lease(m, months, begin, e) - _cum_lease(m, months, begin, s - dt.timedelta(days=1))
        lbc = DP.business_cents(lc, bp)
        return {"depreciation_cents": 0, "depreciation_business_cents": 0, "lease_cents": lc, "lease_business_cents": lbc}
    else:
        return {"depreciation_cents": 0, "depreciation_business_cents": 0, "lease_cents": 0, "lease_business_cents": 0}

