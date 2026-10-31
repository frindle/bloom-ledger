"""Accounting summary for one report period: day rows, totals, entries and the inputs still not set.

Grid rates only; solar credit is not applied. Bookkeeping estimates, not tax advice."""
import bloom_accounting_config as CF
import bloom_accounting_entries as AE
import bloom_accounting_periods as PR
import bloom_accounting_report as RP

GRID_NOTE = "grid rates, solar credit not applied"


def build(db, today, period, machine=None):
    settings = CF.effective_settings(db, today)["values"]
    start, end = PR.report_range(period, today)
    rows = RP.day_rows(db, settings["local_timezone"], start, end, machine, settings)
    t = RP.totals(rows)
    entries = AE.all_entries(db, start, end)
    if machine is not None:
        entries = [e for e in entries if e.get("machine_id") is None or e.get("machine_id") == machine]
    not_set = []
    if t["cost_micro"] is None:
        not_set.append("rate_schedule")
    return {
        "period": period,
        "start": start,
        "end": end,
        "machine": machine,
        "days": rows,
        "totals": t,
        "entries": entries,
        "power": {"basis": "metered" if t["minutes"] else "none", "estimated": False, "note": GRID_NOTE},
        "not_set": not_set,
    }
