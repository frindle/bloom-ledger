"""The /settings/accounting page: a form for the accounting inputs (power rates, lease, hardware depreciation method and elections).

Each input is saved as one append-only, effective-dated row through POST /v1/accounting/settings. Bookkeeping, not tax advice."""


def settings_form_script():
    """JavaScript (no <script> tags) for the accounting settings form: buildUpdates(items, effective) and sendUpdates(updates)."""
    return """
function buildUpdates(items, effective) {
  var out = [];
  items.forEach(function (it) {
    var raw = String(it.raw).trim();
    if (raw === "") { return; }
    var value = raw;
    try {
      if (it.type === "int") { value = Number(raw); if (!Number.isInteger(value)) { throw new Error("not an integer"); } }
      else if (it.type === "json") { value = JSON.parse(raw); }
    } catch (e) { throw new Error(it.key + ": " + e.message); }
    out.push({key: it.key, value: value, effective_from: effective});
  });
  return out;
}
function sendUpdates(updates) {
  return updates.reduce(function (p, u) {
    return p.then(function (done) {
      return fetch("/v1/accounting/settings", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(u)})
        .then(function (r) { if (!r.ok) { throw new Error(u.key + ": HTTP " + r.status); } return done.concat([u.key]); });
    });
  }, Promise.resolve([]));
}
"""


def settings_form_wiring():
    """JavaScript (no <script> tags) that connects #acct-form to buildUpdates and sendUpdates and reports the outcome in #status."""
    return """
document.getElementById("acct-form").addEventListener("submit", function (ev) {
  ev.preventDefault();
  var status = document.getElementById("status");
  var items = Array.prototype.map.call(document.querySelectorAll("[data-key]"), function (el) {
    return {key: el.getAttribute("data-key"), type: el.getAttribute("data-type") || "text", raw: el.value};
  });
  try {
    sendUpdates(buildUpdates(items, document.getElementById("effective-from").value))
      .then(function (keys) { status.textContent = "Saved: " + (keys.join(", ") || "nothing to save"); })
      .catch(function (e) { status.textContent = "Failed: " + e.message; });
  } catch (e) { status.textContent = "Failed: " + e.message; }
});
"""


def settings_form_rows():
    L = "<"
    R = ">"
    Q = chr(34)
    fields = [
        ("dep_method", "Depreciation method", "text", "select"),
        ("dep_life_months", "Straight-line life (months)", "int", "input"),
        ("m4_in_service_date", "Placed in service (YYYY-MM-DD)", "text", "input"),
        ("rate_schedule", "Electricity rate schedule (JSON)", "json", "textarea"),
        ("rate_adder_usd_per_kwh", "Rate adder (USD per kWh)", "text", "input"),
        ("universal_charge_usd_per_kwh", "Universal charge (USD per kWh)", "text", "input"),
        ("county_fee_pct", "County fee (percent)", "text", "input"),
        ("m5_lease_monthly_cents", "Lease payment per month (cents)", "int", "input"),
        ("m5_lease_months", "Lease term (months)", "int", "input"),
        ("m5_lease_start", "Lease start (YYYY-MM-DD)", "text", "input"),
        ("machines", "Machine records, owned or leased (JSON list)", "json", "textarea"),
    ]
    rows = []
    for key, label, dtype, widget in fields:
        rid = "f-" + key
        p_open = L + "p" + R
        p_close = L + "/p" + R
        lbl = L + "label for=" + Q + rid + Q + ">" + label + L + "/label" + R
        ctl = ""
        if widget == "input":
            ctl = L + "input id=" + Q + rid + Q + " data-key=" + Q + key + Q + " data-type=" + Q + dtype + Q + R
            rows.append(p_open + lbl + ctl + p_close)
        elif widget == "textarea":
            ctl = L + "textarea id=" + Q + rid + Q + " data-key=" + Q + key + Q + " data-type=" + Q + dtype + Q + ">" + L + "/textarea" + R
            rows.append(p_open + lbl + ctl + p_close)
        elif widget == "select":
            opt = (L + "option value=" + Q + Q + ">" + "(leave unchanged)" + L + "/option" + R +
                   L + "option value=" + Q + "macrs5" + Q + ">" + "5-year MACRS" + L + "/option" + R +
                   L + "option value=" + Q + "straight_line" + Q + ">" + "Straight line" + L + "/option" + R +
                   L + "option value=" + Q + "section179" + Q + ">" + "Section 179" + L + "/option" + R)
            ctl = L + "select id=" + Q + rid + Q + " data-key=" + Q + key + Q + " data-type=" + Q + dtype + Q + ">" + opt + L + "/select" + R
            rows.append(p_open + lbl + ctl + p_close)
    return "\n".join(rows)
