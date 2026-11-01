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
    """Depreciation (cents) of one asset record for the inclusive range start..end (ISO dates), elections first.

    Section 179 and bonus amounts are expensed whole on the placed_in_service day; the rest follows asset["method"]."""
    basis, ins = asset["basis_cents"], asset["placed_in_service"]
    method = asset.get("method", "macrs5")
    if method not in ("macrs5", "straight_line", "section179"):
        raise ValueError(f"unknown method: {method}")
    if method == "macrs5" and (asset.get("class", "5-year") != "5-year" or asset.get("convention", "half_year") != "half_year"):
        raise ValueError("unsupported class or convention")
    bonus_bp = asset.get("bonus_bp", 0)
    if not isinstance(bonus_bp, int) or isinstance(bonus_bp, bool) or bonus_bp < 0 or bonus_bp > 10000:
        raise ValueError("bad bonus_bp")
    first = basis if method == "section179" else min(asset.get("section179_cents", 0), basis)
    first += (basis - first) * bonus_bp // 10000
    rest = basis - first
    total = section179_cents(first, ins, start, end)
    if method == "straight_line":
        total += straight_line_cents(rest, asset.get("life_months", 60), ins, start, end)
    elif method == "macrs5":
        total += macrs5_cents(rest, ins, start, end)
    return total


def asset_business_cents(asset, start, end, default_bp=None):
    """Depreciation (cents) for one asset, reduced by yearly business-use percent."""
    from_date = dt.date.fromisoformat(start)
    to_date = dt.date.fromisoformat(end)
    total = 0
    year_start = from_date
    while year_start <= to_date:
        year = year_start.year
        year_end = dt.date(year, 12, 31)
        slice_end = min(year_end, to_date)
        dep = asset_depreciation_cents(asset, year_start.isoformat(), slice_end.isoformat())
        bu = asset.get("business_use_bp", {})
        if str(year) in bu:
            bp = bu[str(year)]
        elif default_bp is not None:
            bp = default_bp
        else:
            bp = 10000
        total += business_cents(dep, bp)
        year_start = dt.date(year + 1, 1, 1)
    return total
