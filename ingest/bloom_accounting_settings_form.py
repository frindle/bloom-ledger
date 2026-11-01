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
    """HTML for the accounting setting fields: one <p> per field with a label and a data-key control, joined by newlines."""
    fields = [("dep_method", "Depreciation method", "text", "select"), ("dep_life_months", "Straight-line life (months)", "int", "input"),
              ("m4_in_service_date", "Placed in service (YYYY-MM-DD)", "text", "input"),
              ("rate_schedule", "Electricity rate schedule (JSON)", "json", "textarea"),
              ("rate_adder_usd_per_kwh", "Rate adder (USD per kWh)", "text", "input"),
              ("universal_charge_usd_per_kwh", "Universal charge (USD per kWh)", "text", "input"),
              ("county_fee_pct", "County fee (percent)", "text", "input"),
              ("m5_lease_monthly_cents", "Lease payment per month (cents)", "int", "input"), ("m5_lease_months", "Lease term (months)", "int", "input"),
              ("m5_lease_start", "Lease start (YYYY-MM-DD)", "text", "input"),
              ("machines", "Machine records, owned or leased (JSON list)", "json", "textarea")]
    rows = []
    for key, label, kind, widget in fields:
        attrs = 'id="f-%s" data-key="%s" data-type="%s"' % (key, key, kind)
        if widget == "select":
            ctl = "<select %s>%s</select>" % (attrs, '<option value="">(leave unchanged)</option><option value="macrs5">5-year MACRS</option>'
                                              '<option value="straight_line">Straight line</option><option value="section179">Section 179</option>')
        else:
            ctl = "<%s %s></%s>" % (widget, attrs, widget) if widget == "textarea" else "<input %s>" % attrs
        rows.append('<p><label for="f-%s">%s</label> %s</p>' % (key, label, ctl))
    return "\n".join(rows)


def settings_form_page():
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Accounting settings</title>
<style>
body { font-family: sans-serif; max-width: 40em; margin: 2em auto; }
label { display: block; margin-top: 0.5em; }
input, select, textarea { margin-top: 0.25em; }
</style>
</head>
<body>
<h1>Accounting settings</h1>
<p><strong>Bookkeeping, not tax advice.</strong> Confirm with CPA: depreciation method, elections and business-use figures.</p>
<form id="acct-form">
<p><label for="effective-from">Effective from (YYYY-MM-DD)</label> <input id="effective-from" required></p>
""" + settings_form_rows() + """<p><button type="submit">Save changed fields</button> <span id="status" role="status"></span></p>
</form>
<p>Blank fields are left unchanged. Each save adds a new dated row; earlier rows are kept.</p>
<script>""" + settings_form_script() + settings_form_wiring() + """</script>
</body>
</html>"""
