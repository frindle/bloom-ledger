"""Tax-year bookkeeping view of the ledger: monthly income and business-share expenses, for one calendar year.

Bookkeeping, not tax advice. Money is integer cents or integer micro-USD (1e-6 USD) as the field name says; dates are YYYY-MM-DD."""
import csv
import datetime as dt
import io
import json
import urllib.parse

import bloom_accounting_config as CF
import bloom_accounting_depr as DP
import bloom_accounting_entries as AE
import bloom_accounting_fixed as FX
import bloom_accounting_index as AX
import bloom_accounting_report as RP


def month_shares(year, day_rows):
    result = {}
    for m in range(1, 13):
        key = "%d-%02d" % (year, m)
        result[key] = {"income_micro": 0, "power_micro": 0, "minutes": 0, "paid_minutes": 0, "bp": None}
    for r in day_rows:
        d = r["date"][:7]
        if d.startswith(str(year) + "-"):
            k = d
            v = result[k]
            v["income_micro"] += r["earned_micro"]
            v["minutes"] += r["minutes"]
            v["paid_minutes"] += r["paid_minutes"]
            cm = r.get("cost_micro")
            if cm is not None:
                if v["power_micro"] is not None:
                    v["power_micro"] += cm
            else:
                v["power_micro"] = None
    for k, v in result.items():
        if v["minutes"] == 0:
            v["bp"] = None
        else:
            v["bp"] = v["paid_minutes"] * 10000 // v["minutes"]
    return result

