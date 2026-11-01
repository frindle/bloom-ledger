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
    return """
document.getElementById("acct-form").addEventListener("submit", function(ev) {
  ev.preventDefault();
  try {
    var items = Array.prototype.map.call(document.querySelectorAll("[data-key]"), function(el) {
      return {key: el.getAttribute("data-key"), type: el.getAttribute("data-type") || "text", raw: el.value};
    });
    var effective = document.getElementById("effective-from").value;
    sendUpdates(buildUpdates(items, effective)).then(function(keys) {
      if (keys.length === 0) {
        document.getElementById("status").textContent = "Saved: nothing to save";
      } else {
        document.getElementById("status").textContent = "Saved: " + keys.join(", ");
      }
    }).catch(function(e) {
      document.getElementById("status").textContent = "Failed: " + e.message;
    });
  } catch (e) {
    document.getElementById("status").textContent = "Failed: " + e.message;
  }
});
"""
