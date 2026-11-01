"""Frozen test: bloom_accounting_tax.tax_csv. Fake numbers."""
import bloom_accounting_tax as T

BIZ = {"year": 2026, "view": "business", "disclaimer": "Bookkeeping, not tax advice",
       "months": [{"month": "2026-10", "income_micro": 900, "bp": 5000, "expenses_micro": 6, "net_micro": 894},
                  {"month": "2026-11", "income_micro": 100, "bp": None, "expenses_micro": None, "net_micro": None}],
       "totals": {"income_micro": 1000, "expenses_micro": None, "net_micro": None}}


def test_business_csv_rows_header_total_and_disclaimer():
    lines = T.tax_csv(BIZ).split("\n")
    assert lines[0] == "month,income_micro,bp,expenses_micro,net_micro"
    assert lines[1] == "2026-10,900,5000,6,894" and lines[2] == "2026-11,100,,,"
    assert lines[3] == "TOTAL,1000,,," and lines[4] == '"Bookkeeping, not tax advice"'


def test_hobby_csv_has_income_columns_only_and_trailing_newline():
    hobby = {"year": 2026, "view": "hobby", "disclaimer": "Bookkeeping, not tax advice",
             "months": [{"month": "2026-10", "income_micro": 900, "bp": 5000}], "totals": {"income_micro": 900}}
    text = T.tax_csv(hobby)
    assert text.split("\n")[:3] == ["month,income_micro,bp", "2026-10,900,5000", "TOTAL,900,"]
    assert text.endswith("\n") and "expenses" not in text
