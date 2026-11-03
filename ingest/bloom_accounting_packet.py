"""Year-end tax packet: everything a tax preparer needs for one calendar year, as data and as a printable HTML page.

Figures come from the tax-year report (bloom_accounting_tax.build_tax) so the packet always agrees with /tax.
Bookkeeping, not tax advice: the line numbers are suggested Schedule C lines for the preparer to confirm."""
import datetime as dt
import html

import bloom_accounting_config as CF
import bloom_accounting_depr as DP
import bloom_accounting_entries as AE
import bloom_accounting_fixed as FX
import bloom_accounting_report as RP
import bloom_accounting_tax as TX

LINES = (("1", "Gross receipts (Darkbloom pay)"), ("6", "Other income"), ("13", "Depreciation (Form 4562)"), ("16b", "Interest (machine loan)"),
         ("18", "Office expense (software)"), ("20a", "Rent or lease of equipment"), ("22", "Supplies"),
         ("25", "Utilities (metered electricity, internet)"), ("27a", "Other expenses"))
METHOD_LABEL = {"macrs5": "5-year MACRS, half-year", "straight_line": "Straight line", "section179": "Section 179"}
CATEGORY_LINE = {"hardware": "13", "software": "18", "supplies": "22", "electricity": "25", "internet": "25", "interest": "16b", "other": "27a"}
DISCLAIMER = "Bookkeeping, not tax advice. Line numbers are suggestions for your tax preparer."

# Page shell; packet_html fills the %-slots in order: year, year, prepared, disclaimer, lines rows, use paragraph, year,
# asset rows, entry rows, to-confirm list. Every slot value must already be escaped.
TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tax packet %d</title>
<style>
body { font: 11pt/1.45 Georgia, "Times New Roman", serif; color: #1a1a1a; max-width: 54rem; margin: 2rem auto; padding: 0 1rem; }
h1 { font-size: 1.6rem; margin: 0; } h2 { font-size: 1.1rem; margin: 1.8rem 0 .4rem; border-bottom: 1px solid #999; }
table { border-collapse: collapse; width: 100%%; font-size: 10pt; } th, td { padding: .2rem .45rem; text-align: left; vertical-align: top; }
th { border-bottom: 1px solid #666; } td.num, th.num { text-align: right; white-space: nowrap; } td.d { white-space: nowrap; } tr.total td { border-top: 1px solid #666; font-weight: bold; }
.meta { color: #555; } @media print { body { margin: 0; max-width: none; } h2 { break-after: avoid; } tr { break-inside: avoid; } }
</style></head><body>
<h1>Tax packet, %d</h1>
<p class="meta">Darkbloom inference provider income and expenses. Prepared %s.</p>
<p><strong>%s</strong></p>
<h2>Schedule C summary</h2>
<table><thead><tr><th>Line</th><th>Item</th><th class="num">Amount</th></tr></thead><tbody>%s</tbody></table>
<h2>Business use of the machine</h2>
%s
<h2>Depreciation schedule</h2>
<table><thead><tr><th>Bought</th><th>Vendor</th><th>In service</th><th>Method</th><th class="num">Basis</th><th class="num">%d depreciation</th></tr></thead><tbody>%s</tbody></table>
<h2>Income and expense entries</h2>
<table><thead><tr><th>Date</th><th>Vendor</th><th>Purpose</th><th>Category</th><th>Line</th><th class="num">Amount</th><th class="num">Business</th><th class="num">Counts</th><th>Receipt</th></tr></thead><tbody>%s</tbody></table>
<h2>To confirm with your preparer</h2>
%s
</body></html>
"""


def td(v, cls=None):
    """One escaped table cell; None shows empty."""
    return "<td%s>%s</td>" % (' class="%s"' % cls if cls else "", html.escape("" if v is None else str(v)))


def entry_row(e, bp):
    """One packet row for live ledger entry `e`; bp is the business share (basis points or None) of the entry's month.

    deduct_micro is what the entry adds to its line: a receipt adds amount_cents * 10000 to line "6"; a hardware cost adds None (it
    is depreciated, see the asset schedule); any other cost adds TX.entry_amounts_micro([e], date, date, bp)["expensed_micro"] (0 for
    electricity: metered power already counts it). Keys: id, date, kind, category, vendor, purpose, business_pct (100 when missing),
    amount_cents, line, deduct_micro, receipt, needs (the missing or empty ones of vendor, purpose, receipt, in that order)."""
    if e["kind"] == "receipt":
        line, deduct = "6", e["amount_cents"] * 10000
    else:
        line = CATEGORY_LINE[e["category"]]
        if e["category"] == "hardware":
            deduct = None
        else:
            deduct = TX.entry_amounts_micro([e], e["date"], e["date"], bp)["expensed_micro"]
    pct = e.get("business_pct")
    return {"id": e["id"], "date": e["date"], "kind": e["kind"], "category": e["category"], "vendor": e.get("vendor"),
            "purpose": e.get("purpose"), "business_pct": 100 if pct is None else pct, "amount_cents": e["amount_cents"],
            "line": line, "deduct_micro": deduct, "receipt": e.get("receipt"),
            "needs": [k for k in ("vendor", "purpose", "receipt") if not e.get(k)]}


def packet_lines(totals, rows):
    """Suggested Schedule C lines [{"line", "label", "micro"}] in LINES order from tax totals and entry_row rows.

    "1", "6", "13", "20a" are totals income_micro, other_income_micro, depreciation_business_micro, lease_business_micro.
    "16b", "18", "22", "27a" sum `deduct_micro or 0` of the rows with kind "cost" on that line. "25" is None when power_business_micro
    is None, else power_business_micro plus that sum over the line "25" cost rows whose category is "internet"."""
    def cost_sum(line, cats=None):
        return sum(r["deduct_micro"] or 0 for r in rows
                   if r["kind"] == "cost" and r["line"] == line and (cats is None or r["category"] in cats))
    power = totals["power_business_micro"]
    vals = {"1": totals["income_micro"], "6": totals["other_income_micro"], "13": totals["depreciation_business_micro"],
            "16b": cost_sum("16b"), "18": cost_sum("18"), "20a": totals["lease_business_micro"], "22": cost_sum("22"),
            "25": None if power is None else power + cost_sum("25", ("internet",)), "27a": cost_sum("27a")}
    return [{"line": n, "label": label, "micro": vals[n]} for n, label in LINES]


def asset_rows(settings, entries, year, through):
    """Depreciation schedule: one row per entry with kind "cost", category "hardware" and date <= Dec 31 of `year`, in order.

    Keys: id, date, vendor, purpose, basis_cents (FX.entry_business_cents), placed_in_service (the later of the entry date and
    settings m4_in_service_date; the entry date when that is blank), method (settings dep_method), year_cents (DP.depreciation_cents
    with settings dep_life_months for Jan 1 .. min(Dec 31, through); 0 when through is before Jan 1)."""
    start, end = "%d-01-01" % year, "%d-12-31" % year
    stop = min(end, through)
    out = []
    for e in entries:
        if e["kind"] != "cost" or e["category"] != "hardware" or e["date"] > end:
            continue
        basis = FX.entry_business_cents(e)
        placed = max(e["date"], settings.get("m4_in_service_date") or e["date"])
        year_cents = 0 if stop < start else DP.depreciation_cents(settings["dep_method"], basis, placed,
                                                                    settings.get("dep_life_months"), start, stop)
        out.append({"id": e["id"], "date": e["date"], "vendor": e.get("vendor"), "purpose": e.get("purpose"), "basis_cents": basis,
                    "placed_in_service": placed, "method": settings["dep_method"], "year_cents": year_cents})
    return out


def packet_data(db, year, today=None):
    """The packet for calendar `year` as a dict; `today` (YYYY-MM-DD, default the real date) is the prepared date.

    report = TX.build_tax(db, year); eff = CF.effective_settings(db, Dec 31), settings = eff["values"]. Keys: year, prepared,
    lines (packet_lines of report totals and the entries), expenses_micro and net_micro (report totals), entries (entry_row of
    each AE.current_entries(db, Jan 1, Dec 31), bp = that month's report["months"] bp or None), assets (asset_rows over
    AE.current_entries(db), through today), use ({"business_bp", "minutes", "kwh"} of RP.totals(RP.day_rows(db,
    settings["local_timezone"], Jan 1, Dec 31, None, settings))), flags (eff["flags"]), disclaimer (DISCLAIMER)."""
    today = today or dt.date.today().isoformat()
    report = TX.build_tax(db, year)
    eff = CF.effective_settings(db, "%d-12-31" % year)
    settings = eff["values"]
    bp = {m["month"]: m["bp"] for m in report["months"]}
    start, end = "%d-01-01" % year, "%d-12-31" % year
    rows = [entry_row(e, bp.get(e["date"][:7])) for e in AE.current_entries(db, start, end)]
    use = RP.totals(RP.day_rows(db, settings["local_timezone"], start, end, None, settings))
    return {"year": year, "prepared": today, "lines": packet_lines(report["totals"], rows),
            "expenses_micro": report["totals"]["expenses_micro"], "net_micro": report["totals"]["net_micro"], "entries": rows,
            "assets": asset_rows(settings, AE.current_entries(db), year, today),
            "use": {"business_bp": use["business_bp"], "minutes": use["minutes"], "kwh": use["kwh"]},
            "flags": eff["flags"], "disclaimer": DISCLAIMER}


def money(micro):
    """Micro-USD as "$1,234.56": rounded toward zero to the cent, "-$" prefix for negatives; None -> "not set"."""
    if micro is None:
        return "not set"
    cents = abs(micro) // 10000
    return "%s$%s.%02d" % ("-" if micro < 0 else "", "{:,}".format(cents // 100), cents % 100)


def cents_money(cents):
    """Integer cents formatted like money(); None -> "not set"."""
    return money(None if cents is None else cents * 10000)


def packet_html(data):
    """Printable HTML document for a packet_data dict: TEMPLATE filled with escaped values (see TASK for each slot)."""
    y = data["year"]
    lines = "".join("<tr>%s%s%s</tr>" % (td(l["line"]), td(l["label"]), td(money(l["micro"]), "num")) for l in data["lines"])
    lines += '<tr class="total">%s%s%s</tr>' % (td(""), td("Total expenses"), td(money(data["expenses_micro"]), "num"))
    lines += '<tr class="total">%s%s%s</tr>' % (td("31"), td("Net profit"), td(money(data["net_micro"]), "num"))
    u = data["use"]
    share = "not measured" if u["business_bp"] is None else "%d.%02d%%" % (u["business_bp"] // 100, u["business_bp"] % 100)
    use = "<p>Business use: <strong>%s</strong> of %s metered minutes (%s kWh).</p>" % (
        share, "{:,}".format(u["minutes"]), html.escape(str(u["kwh"])))
    assets = "".join("<tr>%s%s%s%s%s%s</tr>" % (
        td(a["date"], "d"), td(a["vendor"]), td(a["placed_in_service"], "d"), td(METHOD_LABEL.get(a["method"], a["method"])),
        td(cents_money(a["basis_cents"]), "num"), td(cents_money(a["year_cents"]), "num"))
        for a in data["assets"]) or '<tr><td colspan="6">No hardware entries</td></tr>'
    line13 = next((l["micro"] for l in data["lines"] if l["line"] == "13"), None)
    assets += '<tr class="total"><td colspan="5">Total %d depreciation; the business-use share goes on line 13: %s</td>%s</tr>' % (
        y, money(line13), td(cents_money(sum(a["year_cents"] for a in data["assets"])), "num"))
    ents = "".join("<tr>%s%s%s%s%s%s%s%s%s</tr>" % (
        td(r["date"], "d"), td(r["vendor"]), td(r["purpose"]), td(r["category"]), td(r["line"]),
        td(cents_money(r["amount_cents"]), "num"), td("%d%%" % r["business_pct"], "num"),
        td("depreciated" if r["deduct_micro"] is None else money(r["deduct_micro"]), "num"),
        td(r["receipt"] or "missing")) for r in data["entries"]) or '<tr><td colspan="9">No entries</td></tr>'
    todo = ["<li>%s</li>" % html.escape(f["reason"]) for f in data["flags"]]
    todo += ["<li>Entry %d (%s): add %s</li>" % (r["id"], html.escape(r["date"]), html.escape(", ".join(r["needs"])))
             for r in data["entries"] if r["needs"]]
    todo_html = "<ul>%s</ul>" % "".join(todo) if todo else "<p>Nothing to confirm.</p>"
    return TEMPLATE % (y, y, html.escape(data["prepared"]), html.escape(data["disclaimer"]), lines, use, y, assets, ents, todo_html)
