"""Accounting summary for one report period: day rows, totals, entries and the inputs still not set.

Grid rates only; solar credit is not applied. Bookkeeping estimates, not tax advice."""
import bloom_accounting_config as CF
import bloom_accounting_depr as DP
import bloom_accounting_entries as AE
import bloom_accounting_fixed as FX
import bloom_accounting_periods as PR
import bloom_accounting_report as RP

GRID_NOTE = "grid rates, solar credit not applied"
RATE_KEYS = ("rate_schedule", "rate_adder_usd_per_kwh", "universal_charge_usd_per_kwh", "county_fee_pct")


def build(db, today, period, machine=None):
    """Summary dict for report period `period` (day, week, month, quarter, ytd, last_year) ending at local date `today`."""
    settings = CF.effective_settings(db, today)["values"]
    start, end = PR.report_range(period, today)
    rows = RP.day_rows(db, settings["local_timezone"], start, end, machine, settings)
    t = RP.totals(rows)
    entries = [e for e in AE.all_entries(db, start, end) if machine is None or e["machine_id"] in (None, machine)]
    not_set = []
    not_set.extend(k for k in RATE_KEYS if settings.get(k) is None)
    leased = machine is None or machine == settings.get("m5_machine_id")
    lease = FX.lease_cents(settings, start, end) if leased else 0
    owned = machine is None or machine != settings.get("m5_machine_id")
    depr = FX.owned_depreciation_cents(settings, AE.current_entries(db), start, end, machine) if owned else 0
    bp = t["business_bp"]
    depr_biz = depr if not depr else (None if bp is None else DP.business_cents(depr, bp))
    parts = (t["cost_micro"], lease, depr_biz)
    net = None if t["cost_micro"] is None or None in parts else t["earned_micro"] - t["cost_micro"] - (lease + depr_biz) * 10000
    net_missing = [k for k, v in (("lease", lease), ("depreciation", depr_biz)) if v is None]
    machines = machine_breakdown(settings, AE.current_entries(db), start, end)
    return {"machines": machines, "lease_cents": lease, "depreciation_cents": depr, "depreciation_business_cents": depr_biz, "net_micro": net,
            "net_missing": net_missing, "period": period, "start": start, "end": end, "machine": machine, "days": rows, "totals": t, "entries": entries,
            "power": {"basis": "metered" if t["minutes"] else "none", "estimated": False, "note": GRID_NOTE},
            "not_set": not_set}


def machine_breakdown(settings, entries, start, end):
    """Per-machine fixed costs for start..end from the machine records in settings; [] when none are configured.

    Each row: {"id", "display_name", "ownership", "depreciation_cents", "lease_cents"} (gross cents, None when an owned machine has no basis)."""
    links = settings.get("entry_machine_links")
    rows = []
    for m in settings.get("machines") or []:
        c = FX.machine_fixed_cents(m, entries, links, start, end)
        rows.append({"id": m["id"], "display_name": m.get("display_name", m["id"]), "ownership": m["ownership"],
                     "depreciation_cents": c["depreciation_cents"], "lease_cents": c["lease_cents"]})
    return rows
