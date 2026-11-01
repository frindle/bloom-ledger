"""Accounting depreciation in integer cents for a date range, using cumulative daily accrual so periods add up exactly.

Dates are YYYY-MM-DD strings, ranges inclusive. Not tax advice; the method is a setting."""
import datetime as dt


def _cum_sl(basis, life_months, in_service, day):
    days = (day - in_service).days + 1
    if days <= 0:
        return 0
    life_days = life_months * 36525 // 1200
    return basis if days >= life_days else basis * days // life_days


def straight_line_cents(basis_cents, life_months, in_service, start, end):
    """Straight-line depreciation (cents) for the inclusive range start..end, accruing daily from in_service."""
    a, s, e = (dt.date.fromisoformat(x) for x in (in_service, start, end))
    return _cum_sl(basis_cents, life_months, a, e) - _cum_sl(basis_cents, life_months, a, s - dt.timedelta(days=1))


MACRS5_BP = (2000, 3200, 1920, 1152, 1152)


def section179_cents(basis_cents, in_service, start, end):
    """Whole basis expensed on the in-service day: basis when in_service lies inside start..end (ISO strings), else 0."""
    return basis_cents if start <= in_service <= end else 0


def macrs5_year_amounts(basis_cents):
    """Six yearly amounts (cents) of 5-year half-year MACRS; the last absorbs rounding so they sum to the basis."""
    first = [basis_cents * bp // 10000 for bp in MACRS5_BP]
    return first + [basis_cents - sum(first)]


def _cum_macrs5(amounts, in_service, day):
    k = day.year - in_service.year
    if day < in_service or k < 0:
        return 0
    if k >= 6:
        return sum(amounts)
    year_end = dt.date(day.year, 12, 31)
    if k == 0:
        num, den = (day - in_service).days + 1, (year_end - in_service).days + 1
    else:
        num, den = day.timetuple().tm_yday, year_end.timetuple().tm_yday
    return sum(amounts[:k]) + amounts[k] * num // den


def macrs5_cents(basis_cents, in_service, start, end):
    """5-year half-year MACRS (cents) for the inclusive range start..end; each year's amount accrues evenly by day."""
    amounts = macrs5_year_amounts(basis_cents)
    a, s, e = (dt.date.fromisoformat(x) for x in (in_service, start, end))
    return _cum_macrs5(amounts, a, e) - _cum_macrs5(amounts, a, s - dt.timedelta(days=1))


def depreciation_cents(method, basis_cents, in_service, life_months, start, end):
    if method == "straight_line":
        return straight_line_cents(basis_cents, life_months, in_service, start, end)
    elif method == "section179":
        return section179_cents(basis_cents, in_service, start, end)
    elif method == "macrs5":
        return macrs5_cents(basis_cents, in_service, start, end)
    else:
        raise ValueError(f"unknown method: {method}")


def business_cents(amount_cents, pct_bp):
    if not isinstance(pct_bp, int) or isinstance(pct_bp, bool) or pct_bp < 0 or pct_bp > 10000:
        raise ValueError("bad pct")
    return amount_cents * pct_bp // 10000


def asset_depreciation_cents(asset, start, end):
    basis = asset.get("basis_cents", 0)
    placed_in_service = asset.get("placed_in_service", "")
    method = asset.get("method", "macrs5")
    life_months = asset.get("life_months", 60)
    section179_cents_val = asset.get("section179_cents", 0)
    bonus_bp = asset.get("bonus_bp", 0)

    # Validation
    if method not in ("macrs5", "straight_line", "section179"):
        raise ValueError(f"unknown method: {method}")
    if method == "macrs5":
        if asset.get("class") is not None and asset["class"] != "5-year":
            raise ValueError("macrs5 requires class='5-year'")
        if asset.get("convention") is not None and asset["convention"] != "half_year":
            raise ValueError("macrs5 requires convention='half_year'")
    if not isinstance(bonus_bp, int) or isinstance(bonus_bp, bool) or bonus_bp < 0 or bonus_bp > 10000:
        raise ValueError("bad bonus_bp")

    a = dt.date.fromisoformat(placed_in_service)
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end)

    # Calculate the elected part
    if method == "section179":
        first = basis
    else:
        first = min(section179_cents_val, basis)
        first += (basis - first) * bonus_bp // 10000

    rest = basis - first

    # Depreciate the remaining basis
    if method == "macrs5":
        return section179_cents(first, a.isoformat(), s.isoformat(), e.isoformat()) + macrs5_cents(rest, a.isoformat(), s.isoformat(), e.isoformat())
    elif method == "straight_line":
        return section179_cents(first, a.isoformat(), s.isoformat(), e.isoformat()) + straight_line_cents(rest, life_months, a.isoformat(), s.isoformat(), e.isoformat())
    else:
        return section179_cents(first, a.isoformat(), s.isoformat(), e.isoformat())
