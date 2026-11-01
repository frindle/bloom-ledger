"""The /tax page: a static HTML document for the tax-year bookkeeping view. It loads its figures from /v1/accounting/tax in the browser.

Bookkeeping, not tax advice."""


def tax_page_script():
    return """function load() {
  var year = document.getElementById("year");
  var view = document.getElementById("view");
  var csv = document.getElementById("csv");
  var json = document.getElementById("json");
  var rows = document.getElementById("rows");
  var print = document.getElementById("print");
  year.addEventListener("change", load);
  view.addEventListener("change", load);
  print.addEventListener("click", function() { window.print(); });
  var q = "/v1/accounting/tax?year=" + year.value + "&view=" + view.value;
  csv.href = q + "&format=csv";
  json.href = q;
  fetch(q).then(function(resp) {
    return resp.json();
  }).then(function(rep) {
    rows.textContent = "";
    var months = rep.months || [];
    var i, m, tr, td, v, j, cols, totalRow;
    cols = ["month", "income_micro", "bp", "power_business_micro", "depreciation_business_micro", "lease_business_micro", "expenses_micro", "net_micro"];
    for (i = 0; i < months.length; i++) {
      m = months[i];
      tr = document.createElement("tr");
      td = document.createElement("td");
      td.textContent = m.month;
      tr.appendChild(td);
      for (j = 1; j < cols.length; j++) {
        td = document.createElement("td");
        v = m[cols[j]];
        if (v === null || v === undefined) {
          td.textContent = "-";
        } else if (cols[j] === "bp") {
          td.textContent = (v / 100).toFixed(0) + "%";
        } else {
          td.textContent = (v / 1000000).toFixed(2);
        }
        tr.appendChild(td);
      }
      rows.appendChild(tr);
    }
    totalRow = Object.assign({month: "TOTAL"}, rep.totals);
    tr = document.createElement("tr");
    td = document.createElement("td");
    td.textContent = totalRow.month;
    tr.appendChild(td);
    for (j = 1; j < cols.length; j++) {
      td = document.createElement("td");
      v = totalRow[cols[j]];
      if (v === null || v === undefined) {
        td.textContent = "-";
      } else if (cols[j] === "bp") {
        td.textContent = (v / 100).toFixed(0) + "%";
      } else {
        td.textContent = (v / 1000000).toFixed(2);
      }
      tr.appendChild(td);
    }
    rows.appendChild(tr);
  });
}
load();"""
