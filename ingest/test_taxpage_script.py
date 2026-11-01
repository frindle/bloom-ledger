"""Frozen test: bloom_accounting_taxpage.tax_page_script (the /tax page JavaScript). Runs it in node against a tiny fake DOM."""
import json
import shutil
import subprocess

import pytest

import bloom_accounting_taxpage as P

REPORT = {"months": [{"month": "2026-10", "income_micro": 2500000, "bp": 5000, "power_business_micro": None, "depreciation_business_micro": 0,
                      "lease_business_micro": 0, "expenses_micro": None, "net_micro": None}], "totals": {"income_micro": 2500000}}
HARNESS = """
const els = {}; const made = [];
function el(id) { return els[id] || (els[id] = {id, value: id === "year" ? "2026" : "business", children: [], listeners: {}, textContent: "",
  addEventListener(n, f) { this.listeners[n] = f; }, appendChild(c) { this.children.push(c); }}); }
global.document = {getElementById: el, createElement: (t) => ({tag: t, children: [], textContent: "", appendChild(c) { this.children.push(c); }})};
global.window = {print() {}};
const urls = []; global.fetch = (u) => { urls.push(u); return Promise.resolve({json: () => Promise.resolve(%s)}); };
%s
setTimeout(() => {
  const rows = el("rows").children.map((tr) => tr.children.map((td) => td.textContent));
  console.log(JSON.stringify({urls, rows, csv: el("csv").href, json: el("json").href, listeners: [el("year"), el("view"), el("print")].map((e) => Object.keys(e.listeners))}));
}, 20);
"""


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_script_renders_rows_and_links():
    src = P.tax_page_script()
    out = subprocess.run(["node", "-e", HARNESS % (json.dumps(REPORT), src)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    res = json.loads(out.stdout)
    assert res["urls"] == ["/v1/accounting/tax?year=2026&view=business"]
    assert res["csv"] == "/v1/accounting/tax?year=2026&view=business&format=csv" and res["json"] == res["urls"][0]
    assert res["rows"][0] == ["2026-10", "2.50", "50%", "-", "0.00", "0.00", "-", "-"]
    assert res["rows"][1][0] == "TOTAL" and res["rows"][1][1] == "2.50"
    assert res["listeners"] == [["change"], ["change"], ["click"]]


def test_script_is_plain_text_without_dom_injection():
    src = P.tax_page_script()
    assert isinstance(src, str) and "/v1/accounting/tax" in src and "fetch(" in src
    assert "<script" not in src and "innerHTML" not in src and "eval(" not in src and "=>" not in src
