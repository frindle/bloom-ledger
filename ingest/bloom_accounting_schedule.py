"""Year-by-year depreciation schedules for machine assets: the schedule table, a state book, disposal gain or loss,
Section 179 recapture and the mid-quarter 40% test. Every number comes from bloom_accounting_depr.asset_depreciation_cents,
so the schedule, the tax page and the tax packet agree. Elections are recorded on the machine, never chosen here.
Bookkeeping estimates, not tax advice: confirm methods and elections with a CPA."""
import bloom_accounting_depr as DP

MAX_YEARS = 60
STATE_KEYS = ("name", "method", "convention", "class", "section179_cents", "bonus_bp", "life_months", "salvage_cents",
              "manual_schedule_cents")


def bonus_in_force_bp(in_service):
    """Federal bonus depreciation rate (basis points) for property placed in service on `in_service` (YYYY-MM-DD).

    TCJA: 100% from 2017-09-28, then 80% (2023), 60% (2024), 40% (2025); the 2025 budget act restored 100% for property
    acquired after 2025-01-19. The real test is the acquisition date, so this is a starting value for the CPA to confirm."""
    if in_service < "2017-09-28":
        return 5000
    if in_service < "2023-01-01":
        return 10000
    if in_service < "2024-01-01":
        return 8000
    if in_service < "2025-01-01":
        return 6000
    if in_service < "2025-01-20":
        return 4000
    return 10000


def state_asset(asset):
    """The asset as a state return sees it: the record's "state" overrides (STATE_KEYS) applied on top; None when the record
    has no state book. A state that does not conform to bonus or Section 179 records bonus_bp 0 / section179_cents 0."""
    st = asset.get("state")
    if not isinstance(st, dict):
        return None
    out = {k: v for k, v in asset.items() if k != "state"}
    out.update({k: v for k, v in st.items() if k in STATE_KEYS and k != "name"})
    return out


def _year_bp(asset, year, default_bp):
    return (asset.get("business_use_bp") or {}).get(str(year), 10000 if default_bp is None else default_bp)


def asset_schedule(asset, default_bp=None, through_year=None):
    """{"years": [{"year", "depreciation_cents", "business_bp", "business_cents", "remaining_basis_cents"}], "total_cents"}.

    One row per calendar year from the in-service year until the basis is used up, the asset is disposed of, or
    through_year; remaining_basis_cents is the gross basis less all depreciation to the end of that year."""
    basis, y0 = asset["basis_cents"], int(asset["placed_in_service"][:4])
    stop = int(asset["disposed_on"][:4]) if asset.get("disposed_on") else y0 + MAX_YEARS
    if through_year is not None:
        stop = min(stop, through_year)
    full = DP.asset_depreciation_cents(asset, asset["placed_in_service"], "%d-12-31" % (y0 + MAX_YEARS))
    rows, cum = [], 0
    for y in range(y0, stop + 1):
        amt = DP.asset_depreciation_cents(asset, "%d-01-01" % y, "%d-12-31" % y)
        cum += amt
        bp = _year_bp(asset, y, default_bp)
        rows.append({"year": y, "depreciation_cents": amt, "business_bp": bp, "business_cents": DP.business_cents(amt, bp),
                     "remaining_basis_cents": basis - cum})
        if cum >= full and not asset.get("disposed_on") and through_year is None:
            break
    return {"years": rows, "total_cents": cum}


def disposal(asset):
    """Sale or retirement result, or None when the asset has no disposed_on.

    {"date", "price_cents", "depreciation_taken_cents", "adjusted_basis_cents", "gain_cents" (negative = loss),
    "recapture_1245_cents" (ordinary income part of a gain), "section_1231_cents"}. Gross amounts; the preparer applies the
    business-use share on Form 4797."""
    if not asset.get("disposed_on"):
        return None
    taken = DP.asset_depreciation_cents(asset, asset["placed_in_service"], asset["disposed_on"])
    adj = asset["basis_cents"] - taken
    price = asset.get("disposal_price_cents") or 0
    gain = price - adj
    rec = min(max(gain, 0), taken)
    return {"date": asset["disposed_on"], "price_cents": price, "depreciation_taken_cents": taken, "adjusted_basis_cents": adj,
            "gain_cents": gain, "recapture_1245_cents": rec, "section_1231_cents": max(gain, 0) - rec}


def section179_recapture(asset, default_bp=None):
    """Estimate when business use drops to 50% or less inside the recovery period after a Section 179 election, else None.

    {"year", "business_bp", "section179_cents", "recomputed_cents", "recapture_cents"}: recapture is the Section 179
    amount less the depreciation the regular method would have allowed on it in the years before (Form 4797 Part IV)."""
    s179, _ = DP.elections_cents(asset)
    if asset.get("method", "macrs5") in ("section179",):
        s179 = asset["basis_cents"]
    if s179 <= 0 or asset.get("method") in ("de_minimis", "manual"):
        return None
    y0 = int(asset["placed_in_service"][:4])
    years = DP.CLASS_YEARS.get(asset.get("class", "5-year"), 5)
    for y in range(y0 + 1, y0 + years + 1):
        bp = _year_bp(asset, y, default_bp)
        if bp <= 5000:
            plain = {k: v for k, v in asset.items() if k not in ("section179_cents", "bonus_bp", "disposed_on", "state")}
            plain.update(basis_cents=s179, method="macrs5" if asset.get("method") == "section179" else asset.get("method", "macrs5"))
            recomputed = DP.asset_depreciation_cents(plain, asset["placed_in_service"], "%d-12-31" % (y - 1))
            return {"year": y, "business_bp": bp, "section179_cents": s179, "recomputed_cents": recomputed,
                    "recapture_cents": s179 - recomputed}
    return None


def mid_quarter_test(assets, year):
    """The 40% test for `year`: {"q4_cents", "total_cents", "q4_bp", "required"} over the assets placed in service that year
    (depreciable basis after Section 179; de minimis and fully expensed assets excluded). required = more than 40% in Q4."""
    total = q4 = 0
    for a in assets:
        if a["placed_in_service"][:4] != str(year) or a.get("method") in ("section179", "de_minimis"):
            continue
        s179, _ = DP.elections_cents(a)
        b = a["basis_cents"] - s179
        total += b
        if a["placed_in_service"][5:7] >= "10":
            q4 += b
    q4_bp = q4 * 10000 // total if total else 0
    return {"q4_cents": q4, "total_cents": total, "q4_bp": q4_bp, "required": q4_bp > 4000}


def asset_flags(asset, default_bp=None, label="This machine"):
    """Plain-language items for the preparer about one asset (list of str)."""
    out = []
    m = asset.get("method", "macrs5")
    if m in ("macrs5", "macrs_150db", "ads", "straight_line") and "bonus_bp" not in asset:
        out.append("%s: bonus depreciation applies by default (%d%% for property placed in service %s) unless you elect out; "
                   "record the bonus percent you use, 0 to elect out" % (label, bonus_in_force_bp(asset["placed_in_service"]) // 100,
                                                                        asset["placed_in_service"]))
    if m == "de_minimis" and asset["basis_cents"] > DP.DE_MINIMIS_LIMIT_CENTS:
        out.append("%s: the de minimis safe harbor is limited to $2,500 per item or invoice" % label)
    if m == "de_minimis":
        out.append("%s: de minimis items are deducted as supplies or other expenses, not on Form 4562" % label)
    if m == "straight_line" and asset.get("salvage_cents"):
        out.append("%s: tax depreciation ignores salvage value; the salvage figure is a book choice" % label)
    if m == "manual":
        out.append("%s: depreciation follows the schedule you entered, used as is" % label)
    r = section179_recapture(asset, default_bp)
    if r:
        out.append("%s: business use is %d%% in %d, 50%% or less, so about $%s of the Section 179 deduction is recaptured as "
                   "income (Form 4797 Part IV)" % (label, r["business_bp"] // 100, r["year"], "{:,.2f}".format(r["recapture_cents"] / 100)))
    d = disposal(asset)
    if d:
        out.append("%s: disposed of %s for $%s; %s of $%s, of which $%s is depreciation recapture (Form 4797)" % (
            label, d["date"], "{:,.2f}".format(d["price_cents"] / 100), "gain" if d["gain_cents"] >= 0 else "loss",
            "{:,.2f}".format(abs(d["gain_cents"]) / 100), "{:,.2f}".format(d["recapture_1245_cents"] / 100)))
    return out

