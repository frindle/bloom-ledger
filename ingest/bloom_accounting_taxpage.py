"""The /tax page: a static HTML document for the tax-year bookkeeping view. It loads its figures from /v1/accounting/tax in the browser.

Bookkeeping, not tax advice."""


def tax_page_script():
    """JavaScript (no <script> tags) for the /tax page: reads #year and #view, fetches the report, fills #rows and the #csv and #json links."""
    return """
var cols = ["month", "income_micro", "bp", "power_business_micro", "depreciation_business_micro", "lease_business_micro", "expenses_micro", "net_micro"];
function money(v) { return v === null || v === undefined ? "-" : (v / 1000000).toFixed(2); }
function pct(v) { return v === null || v === undefined ? "-" : (v / 100).toFixed(0) + "%"; }
function load() {
  var q = "/v1/accounting/tax?year=" + document.getElementById("year").value + "&view=" + document.getElementById("view").value;
  document.getElementById("csv").href = q + "&format=csv";
  document.getElementById("json").href = q;
  fetch(q).then(function (r) { return r.json(); }).then(function (rep) {
    var body = document.getElementById("rows");
    body.textContent = "";
    rep.months.concat([Object.assign({month: "TOTAL"}, rep.totals)]).forEach(function (m) {
      var tr = document.createElement("tr");
      cols.forEach(function (c) {
        var td = document.createElement("td");
        td.textContent = c === "month" ? m[c] : c === "bp" ? pct(m[c]) : money(m[c]);
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  });
}
document.getElementById("year").addEventListener("change", load);
document.getElementById("view").addEventListener("change", load);
document.getElementById("print").addEventListener("click", function () { window.print(); });
load();
"""


def tax_page(year):
    """Full HTML document of the /tax page for calendar `year` (int; ValueError if not an int). Inline style with a print stylesheet, inline script."""
    if isinstance(year, bool) or not isinstance(year, int):
        raise ValueError("bad year")
    years = "".join('<option value="%d"%s>%d</option>' % (y, " selected" if y == year else "", y) for y in range(year - 5, year + 2))
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tax year %d</title>
<style>
body { font-family: system-ui, sans-serif; margin: 1.5rem; }
th, td { padding: .25rem .6rem; text-align: right; } th:first-child, td:first-child { text-align: left; }
@media print { .noprint { display: none; } body { margin: 0; } }
</style></head><body>
<h1>Tax year %d</h1>
<p id="disclaimer"><strong>Bookkeeping, not tax advice.</strong> Confirm figures with your CPA.</p>
<p class="noprint"><label for="year">Year</label> <select id="year">%s</select>
<label for="view">View</label> <select id="view"><option value="business" selected>Business</option><option value="hobby">Hobby (income only)</option></select>
<a id="csv" href="#">CSV</a> <a id="json" href="#">JSON</a> <button id="print" type="button">Print</button></p>
<table id="months"><thead><tr><th>Month</th><th>Income</th><th>Business share</th><th>Power</th><th>Depreciation</th><th>Lease</th><th>Expenses</th><th>Net</th></tr></thead>
<tbody id="rows"></tbody></table>
<script>%s</script>
</body></html>
""" % (year, year, years, tax_page_script())
