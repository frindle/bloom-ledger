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
    lid = machine.get("id")
    link_map = links if links is not None else {}
    total = 0
    found = False
    for e in entries:
        if e.get("kind") != "cost" or e.get("category") != "hardware":
            continue
        mid = link_map.get(str(e["id"]), e.get("machine_id"))
        if mid != lid:
            continue
        total += e["amount_cents"]
        found = True
    if found:
        return total
    return machine.get("purchase_cents")
