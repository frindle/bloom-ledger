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


CLASS_YEARS = {"3-year": 3, "5-year": 5, "7-year": 7}
CONVENTIONS = ("half_year", "mid_quarter")
# macrs5 = GDS 200% declining balance; macrs_150db = 150% declining balance; ads = straight line over the ADS life
# (life_months, default 60); straight_line = book straight line over life_months less salvage_cents; section179 and
# de_minimis expense the whole basis on the in-service day; manual uses manual_schedule_cents {year: cents} verbatim.
METHODS = ("macrs5", "macrs_150db", "ads", "straight_line", "section179", "de_minimis", "manual")
MACRS_FACTOR = {"macrs5": 200, "macrs_150db": 150, "ads": 100}
DE_MINIMIS_LIMIT_CENTS = 250000  # $2,500 per item or invoice (no applicable financial statement)
_FIRST_FRACTION = {"half_year": (6, 12), 1: (21, 24), 2: (15, 24), 3: (9, 24), 4: (3, 24)}
_DISPOSAL_FRACTION = {"half_year": (1, 2), 1: (3, 24), 2: (9, 24), 3: (15, 24), 4: (21, 24)}


def _quarter(date_iso):
    return (int(date_iso[5:7]) - 1) // 3 + 1


def macrs_rates_bp(years, factor_pct, convention="half_year", quarter=None):
    """Yearly MACRS percentages in basis points (years + 1 of them, summing to 10000), built the way the IRS tables are:
    factor_pct declining balance switching to straight line when that is larger, first-year fraction from the convention
    (half_year, or mid_quarter with the in-service quarter 1-4). factor 100 gives straight line (ADS)."""
    from fractions import Fraction as F
    num, den = _FIRST_FRACTION["half_year" if convention == "half_year" else quarter]
    f = F(num, den)
    rate, left, elapsed, cum, out = F(factor_pct, 100 * years), F(1), F(0), F(0), [0]
    for k in range(years + 1):
        if k == years:
            amt = left
        elif k == 0:
            amt = left * rate * f
        else:
            amt = min(left, max(left * rate, left / (years - elapsed)))
        left -= amt
        elapsed += f if k == 0 else 1
        cum += amt
        out.append(int(cum * 10000 + F(1, 2)))  # the IRS tables round the running total, so the rows sum to 100%
    return tuple(out[i + 1] - out[i] for i in range(years + 1))


def _check(asset):
    method = asset.get("method", "macrs5")
    if method not in METHODS:
        raise ValueError(f"unknown method: {method}")
    if asset.get("class", "5-year") not in CLASS_YEARS or asset.get("convention", "half_year") not in CONVENTIONS:
        raise ValueError("unsupported class or convention")
    for k in ("bonus_bp",):
        v = asset.get(k, 0)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0 or v > 10000:
            raise ValueError("bad " + k)
    return method


def elections_cents(asset):
    """(section179, bonus) cents expensed on the in-service day. Whole basis for section179 / de_minimis; none for manual."""
    method, basis = _check(asset), asset["basis_cents"]
    if method in ("section179", "de_minimis"):
        return basis, 0
    if method == "manual":
        return 0, 0
    s179 = min(asset.get("section179_cents", 0) or 0, basis)
    return s179, (basis - s179) * asset.get("bonus_bp", 0) // 10000


def _amounts(asset, rest):
    """Per-calendar-year amounts (list, index 0 = in-service year) of the regular (non-election) depreciation of `rest` cents,
    cut at the disposal year. None for daily straight line (handled separately)."""
    method, ins = asset.get("method", "macrs5"), asset["placed_in_service"]
    disposed = asset.get("disposed_on")
    if method == "manual":
        sched = asset.get("manual_schedule_cents") or {}
        y0 = int(ins[:4])
        last = max([int(y) for y in sched] + [y0])
        amts = [int(sched.get(str(y), 0)) for y in range(y0, last + 1)]
        if disposed:
            amts = amts[:int(disposed[:4]) - y0 + 1]
        return amts
    if method not in MACRS_FACTOR:
        return None
    conv = asset.get("convention", "half_year")
    if method == "ads":
        years_ = max(1, (asset.get("life_months") or 60) // 12)
    else:
        years_ = CLASS_YEARS[asset.get("class", "5-year")]
    rates = macrs_rates_bp(years_, MACRS_FACTOR[method], conv, _quarter(ins))
    amts = [rest * bp // 10000 for bp in rates[:-1]]
    amts.append(rest - sum(amts))
    if disposed:
        d = int(disposed[:4]) - int(ins[:4])
        if d <= 0:
            return [0]
        if d < len(amts) - 1:
            n, dn = _DISPOSAL_FRACTION["half_year" if conv == "half_year" else _quarter(disposed)]
            amts = amts[:d] + [amts[d] * n // dn]
    return amts


def _cum_years(amounts, in_service, disposed, day):
    total = 0
    for k, amt in enumerate(amounts):
        y = in_service.year + k
        lo = in_service if k == 0 else dt.date(y, 1, 1)
        hi = disposed if disposed is not None and disposed.year == y else dt.date(y, 12, 31)
        if day < lo:
            break
        if day >= hi:
            total += amt
            continue
        total += amt * ((day - lo).days + 1) // ((hi - lo).days + 1)
        break
    return total


def _cum_asset(asset, day):
    ins = dt.date.fromisoformat(asset["placed_in_service"])
    disposed = dt.date.fromisoformat(asset["disposed_on"]) if asset.get("disposed_on") else None
    s179, bonus = elections_cents(asset)
    first = s179 + bonus
    if asset.get("disposed_on") and asset["disposed_on"][:4] == asset["placed_in_service"][:4]:
        first = s179  # no bonus for property disposed of in the year it was placed in service
    total = first if day >= ins else 0
    rest = asset["basis_cents"] - s179 - bonus
    amounts = _amounts(asset, rest)
    if amounts is not None:
        return total + _cum_years(amounts, ins, disposed, day)
    if asset.get("method", "macrs5") == "straight_line":
        rest -= min(asset.get("salvage_cents", 0) or 0, rest)
        stop = min(day, disposed) if disposed is not None else day
        return total + _cum_sl(rest, asset.get("life_months", 60), ins, stop)
    return total


def asset_depreciation_cents(asset, start, end):
    """Depreciation (cents) of one asset record for the inclusive range start..end (ISO dates), elections first.

    Section 179 and bonus amounts are expensed whole on the placed_in_service day; the rest follows asset["method"]
    (see METHODS), its class and convention, and stops at disposed_on when set."""
    _check(asset)
    s = dt.date.fromisoformat(start)
    return _cum_asset(asset, dt.date.fromisoformat(end)) - _cum_asset(asset, s - dt.timedelta(days=1))


def asset_business_cents(asset, start, end, default_bp=None):
    """Business-use part (cents) of asset_depreciation_cents for start..end, applying the asset's yearly business-use percent.

    asset["business_use_bp"] maps a year string to basis points; a year not listed uses default_bp, else 10000 (all business)."""
    shares = asset.get("business_use_bp", {})
    s, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    total = 0
    for year in range(s.year, e.year + 1):
        lo, hi = max(s, dt.date(year, 1, 1)), min(e, dt.date(year, 12, 31))
        bp = shares.get(str(year), 10000 if default_bp is None else default_bp)
        total += business_cents(asset_depreciation_cents(asset, lo.isoformat(), hi.isoformat()), bp)
    return total


def new_asset_defaults():
    """Fields a newly added asset starts with: 5-year MACRS, half-year, no elections, flagged for a CPA to confirm.

    Old records keep whatever method they already carry (for example straight_line over 60 months)."""
    return {"method": "macrs5", "class": "5-year", "convention": "half_year", "life_months": 60,
            "section179_cents": 0, "bonus_bp": 0, "business_use_bp": {}, "cpa_flag": "confirm with CPA"}
