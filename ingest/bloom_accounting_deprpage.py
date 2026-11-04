"""The /settings/depreciation page and GET /v1/accounting/depreciation: per-machine depreciation records and their schedules.

The page edits the depreciation fields of the "machines" accounting setting (method, class, convention, Section 179, bonus,
life, salvage, disposal, business use by year, a manual schedule and a separate state book) and saves the whole list as one
new effective-dated row through POST /v1/accounting/settings. Elections are recorded, never chosen here. Bookkeeping, not
tax advice: confirm methods and elections with a CPA."""
import datetime as dt

import bloom_accounting_config as CF
import bloom_accounting_entries as AE
import bloom_accounting_fixed as FX
import bloom_accounting_packet as PK
import bloom_accounting_schedule as SC


def _latest_machines_from(db):
    CF.create_settings_table(db)
    row = db.execute("SELECT MAX(effective_from) FROM acct_settings WHERE key = 'machines'").fetchone()
    return row[0] if row else None


def seed_machines(settings, profiles):
    """Suggested owned machine records when no machine records exist: from Settings machine profiles marked owned with a
    purchase price and in-service date, else from the legacy M4 depreciation settings. Nothing is saved until the user saves."""
    out = []
    for mid, p in sorted((profiles or {}).items()):
        if p.get("acquisition") == "owned" and p.get("purchase_cents") and p.get("in_service"):
            out.append({"id": mid, "display_name": p.get("display_name") or mid, "processor": p.get("model") or mid,
                        "ownership": "owned", "in_service": p["in_service"], "business_mode": "auto_paid_hours",
                        "purchase_cents": p["purchase_cents"], "depreciation_method": "macrs5"})
    if not out and settings.get("m4_in_service_date"):
        out.append({"id": "m4", "display_name": "M4", "processor": "M4", "ownership": "owned",
                    "in_service": settings["m4_in_service_date"], "business_mode": "auto_paid_hours",
                    "purchase_cents": None, "depreciation_method": settings.get("dep_method") or "macrs5"})
    return out


def _schedule(asset, default_bp):
    return {"method_label": PK.method_label(asset), "years": SC.asset_schedule(asset, default_bp)["years"]}


def depreciation_data(db, profiles=None, today=None):
    """{"machines", "seeded", "effective_from", "assets", "mid_quarter", "disclaimer"} for the page.

    machines: the latest "machines" record list (all of them, leased too, so a save keeps them), else seed_machines (seeded
    True). assets: per owned machine with a basis {"id", "name", "basis_cents", "bonus_in_force_bp", "federal", "state",
    "disposal", "flags"}; machines without a basis appear with basis_cents None and no schedule. mid_quarter: the 40% test
    for each in-service year."""
    today = today or dt.date.today().isoformat()
    settings = CF.effective_settings(db, "9999-12-31")["values"]
    machines = settings.get("machines") or []
    seeded = not machines
    if seeded:
        machines = seed_machines(settings, profiles)
        settings = dict(settings, machines=machines)
    entries = AE.current_entries(db)
    pairs = PK.machine_assets(settings, entries)
    with_basis = {m["id"] for m, _ in pairs}
    assets = []
    for m, a in pairs:
        st = SC.state_asset(a)
        assets.append({"id": m["id"], "name": m.get("display_name", m["id"]), "basis_cents": a["basis_cents"],
                       "bonus_in_force_bp": SC.bonus_in_force_bp(a["placed_in_service"]), "federal": _schedule(a, None),
                       "state": None if st is None else dict(_schedule(st, None), name=a["state"].get("name") or "State"),
                       "disposal": SC.disposal(a), "flags": SC.asset_flags(a, None, m.get("display_name", m["id"]))})
    for m in machines:
        if m.get("ownership") == "owned" and m.get("id") not in with_basis:
            assets.append({"id": m.get("id"), "name": m.get("display_name") or m.get("id"), "basis_cents": None,
                           "bonus_in_force_bp": SC.bonus_in_force_bp(m["in_service"]) if m.get("in_service") else None,
                           "federal": None, "state": None, "disposal": None,
                           "flags": ["%s: no purchase price or hardware cost entry, so nothing to depreciate yet"
                                     % (m.get("display_name") or m.get("id"))]})
    years = sorted({int(a["placed_in_service"][:4]) for _, a in pairs})
    mq = [dict(SC.mid_quarter_test([a for _, a in pairs], y), year=y) for y in years]
    ins = sorted(m["in_service"] for m in machines if m.get("in_service"))
    eff = _latest_machines_from(db) or (ins[0] if ins else today)
    return {"machines": machines, "seeded": seeded, "effective_from": eff, "assets": assets, "mid_quarter": mq,
            "disclaimer": "Bookkeeping estimates, not tax advice. Confirm methods and elections with a CPA."}


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Depreciation</title>
<style>
:root { --paper:#e9efec; --card:#f6f9f7; --ink:#12211d; --muted:#4d625b; --rule:#a9bbb4; --sealed:#0e6b5b; --waiting:#b7791f;
  --missing:#9b2c2c; --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; --mono:ui-monospace,Menlo,monospace; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font-family: var(--serif); line-height: 1.5; }
main { max-width: 64rem; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
h1 { font-size: 2rem; margin: 0 0 .25rem; font-weight: 600; }
h2 { font-size: 1.35rem; margin: 0 0 .5rem; }
h3 { font-size: 1.05rem; margin: 1.25rem 0 .4rem; }
.lede { color: var(--muted); max-width: 44rem; margin: 0 0 1rem; }
.nav a { color: var(--sealed); margin-right: 1rem; }
section.machine { background: var(--card); border: 1px solid var(--rule); border-left: 4px solid var(--sealed); padding: 1rem 1.25rem;
  margin: 1.25rem 0; border-radius: 3px; }
section.machine.nobasis { border-left-color: var(--waiting); }
.basis { color: var(--muted); margin: 0 0 .75rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(13rem, 1fr)); gap: .6rem 1rem; }
label { display: flex; flex-direction: column; font-size: .9rem; color: var(--muted); }
input, select, textarea { font: inherit; color: var(--ink); background: #fff; border: 1px solid var(--rule); padding: .3rem .4rem; border-radius: 2px; }
textarea { min-height: 4.5rem; font-family: var(--mono); font-size: .85rem; }
input:focus, select:focus, textarea:focus, button:focus { outline: 2px solid var(--sealed); outline-offset: 1px; }
fieldset { border: 1px dashed var(--rule); margin: .9rem 0 0; padding: .6rem .9rem .9rem; }
legend { color: var(--ink); padding: 0 .3rem; }
.hint { font-size: .8rem; color: var(--muted); }
table { border-collapse: collapse; width: 100%; margin: .25rem 0; font-size: .92rem; }
th, td { padding: .25rem .5rem; border-bottom: 1px solid var(--rule); text-align: right; }
th:first-child, td:first-child { text-align: left; }
th { font-weight: 600; color: var(--muted); }
td.num { font-variant-numeric: tabular-nums; }
ul.flags { margin: .5rem 0 0; padding-left: 1.2rem; }
ul.flags li { margin: .2rem 0; }
.warn { color: var(--missing); }
.bar { position: sticky; bottom: 0; background: var(--paper); border-top: 1px solid var(--rule); padding: .75rem 0; display: flex;
  gap: 1rem; align-items: center; flex-wrap: wrap; }
button { font: inherit; background: var(--sealed); color: #fff; border: 0; padding: .45rem 1.1rem; border-radius: 2px; cursor: pointer; }
#status.err { color: var(--missing); }
</style></head><body><main>
<p class="nav"><a href="/settings">Settings</a><a href="/settings/accounting">Accounting settings</a><a href="/tax">Tax</a></p>
<h1>Depreciation</h1>
<p class="lede">How each owned machine is written off, year by year. Record the elections you or your CPA chose; nothing here
picks one for you. Bookkeeping estimates, not tax advice.</p>
<div id="seeded" hidden><p class="warn">No machine records are saved yet. These were filled in from your machine settings;
check them and save to start keeping depreciation records.</p></div>
<div id="mq"></div>
<form id="dep-form"><div id="machines"></div>
<div class="bar"><label>Applies from <input id="effective-from" required pattern="\d{4}-\d{2}-\d{2}"></label>
<button type="submit">Save depreciation records</button><span id="status" role="status"></span></div></form>
<p class="hint">Each save adds a new dated record of all machines; earlier records are kept. The tax packet for a year uses the
record in force on December 31 of that year.</p>
</main>
<script>
var METHODS = [["macrs5","MACRS 200% declining balance"],["macrs_150db","MACRS 150% declining balance"],["ads","ADS straight line"],
  ["straight_line","Straight line (any life, salvage)"],["section179","Section 179, full cost"],["de_minimis","De minimis safe harbor ($2,500)"],
  ["manual","Manual schedule"]];
var CLASSES = ["3-year","5-year","7-year"], DATA = null;
function el(tag, attrs, kids) {
  var e = document.createElement(tag);
  Object.keys(attrs || {}).forEach(function (k) { if (k === "text") { e.textContent = attrs[k]; } else { e.setAttribute(k, attrs[k]); } });
  (kids || []).forEach(function (c) { e.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
  return e;
}
function money(c) { return c == null ? "" : "$" + (c / 100).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2}); }
function dollarsIn(c) { return c == null ? "" : (c / 100).toFixed(2); }
function pctIn(bp) { return bp == null ? "" : String(bp / 100); }
function field(label, input, hint) { return el("label", {}, [label, input].concat(hint ? [el("span", {"class": "hint", text: hint})] : [])); }
function input(name, value, attrs) { var i = el("input", Object.assign({name: name}, attrs || {})); i.value = value == null ? "" : value; return i; }
function select(name, opts, value, blank) {
  var s = el("select", {name: name});
  if (blank) { s.appendChild(el("option", {value: "", text: blank})); }
  opts.forEach(function (o) { var v = Array.isArray(o) ? o[0] : o; s.appendChild(el("option", {value: v, text: Array.isArray(o) ? o[1] : o})); });
  s.value = value == null ? "" : value;
  return s;
}
function yearMap(obj, fmt) { return Object.keys(obj || {}).sort().map(function (y) { return y + ": " + fmt(obj[y]); }).join("\n"); }
function scheduleTable(sc) {
  var t = el("table", {}, [el("tr", {}, ["Year","Depreciation","Business share","Business amount","Basis left"].map(function (h) { return el("th", {text: h}); }))]);
  sc.years.forEach(function (r) {
    t.appendChild(el("tr", {}, [el("td", {text: String(r.year)}), el("td", {"class": "num", text: money(r.depreciation_cents)}),
      el("td", {"class": "num", text: r.business_bp == null ? "measured" : (r.business_bp / 100) + "%"}),
      el("td", {"class": "num", text: r.business_cents == null ? "" : money(r.business_cents)}),
      el("td", {"class": "num", text: money(r.remaining_basis_cents)})]));
  });
  return t;
}
function machineCard(m, a) {
  var form = el("div", {"class": "grid"});
  var bonusHint = a && a.bonus_in_force_bp != null ? "Rate in force for this date: " + a.bonus_in_force_bp / 100 + "%. 0 elects out." : "0 elects out.";
  var bonus = m.bonus_bp != null ? m.bonus_bp : (a ? a.bonus_in_force_bp : null);
  form.appendChild(field("Method", select("depreciation_method", METHODS, m.depreciation_method || "macrs5")));
  form.appendChild(field("Recovery class", select("class", CLASSES, m["class"], "5-year (default)")));
  form.appendChild(field("Convention", select("convention", [["half_year","Half-year"],["mid_quarter","Mid-quarter"]], m.convention, "Half-year (default)")));
  form.appendChild(field("Placed in service", input("in_service", m.in_service, {pattern: "\\d{4}-\\d{2}-\\d{2}", required: ""})));
  form.appendChild(field("Purchase price ($)", input("purchase_cents", dollarsIn(m.purchase_cents), {inputmode: "decimal"}), "Hardware cost entries override this."));
  form.appendChild(field("Section 179 ($)", input("section179_cents", dollarsIn(m.section179_cents), {inputmode: "decimal"}), "Partial amounts allowed."));
  form.appendChild(field("Bonus (%)", input("bonus_bp", pctIn(bonus), {inputmode: "decimal"}), bonusHint + (m.bonus_bp == null ? " Prefilled, not yet recorded: the schedule below uses 0% until you save." : "")));
  form.appendChild(field("Life (months)", input("life_months", m.life_months, {inputmode: "numeric"}), "Straight line and ADS."));
  form.appendChild(field("Salvage value ($)", input("salvage_cents", dollarsIn(m.salvage_cents), {inputmode: "decimal"}), "Straight line only; a book figure."));
  form.appendChild(field("Sold or retired on", input("disposed_on", m.disposed_on, {pattern: "\\d{4}-\\d{2}-\\d{2}", placeholder: "YYYY-MM-DD"})));
  form.appendChild(field("Sale price ($)", input("disposal_price_cents", dollarsIn(m.disposal_price_cents), {inputmode: "decimal"})));
  var more = el("div", {"class": "grid"});
  more.appendChild(field("Business use by year (%)", el("textarea", {name: "business_use_bp", placeholder: "2026: 90\n2027: 85"}), "Blank years use the measured share."));
  more.appendChild(field("Manual schedule ($ by year)", el("textarea", {name: "manual_schedule_cents", placeholder: "2026: 1200.00\n2027: 800.00"}), "Used as is when the method is Manual schedule."));
  more.querySelector("[name=business_use_bp]").value = yearMap(m.business_use_bp, function (v) { return v / 100; });
  more.querySelector("[name=manual_schedule_cents]").value = yearMap(m.manual_schedule_cents, function (v) { return (v / 100).toFixed(2); });
  var st = m.state || {}, stBox = el("input", {type: "checkbox", name: "state_on"}); stBox.checked = !!m.state;
  var stGrid = el("div", {"class": "grid"}, [field("State", input("state_name", st.name, {placeholder: "California"})),
    field("State method", select("state_method", METHODS, st.method, "Same as federal")),
    field("State Section 179 ($)", input("state_section179_cents", dollarsIn(st.section179_cents), {inputmode: "decimal"}), "Blank = same as federal."),
    field("State bonus (%)", input("state_bonus_bp", pctIn(st.bonus_bp), {inputmode: "decimal"}), "0 if the state does not allow bonus."),
    field("State life (months)", input("state_life_months", st.life_months, {inputmode: "numeric"}))]);
  var stSet = el("fieldset", {}, [el("legend", {}, [el("label", {style: "flex-direction:row;gap:.4rem;color:var(--ink)"}, [stBox, "Keep a separate state schedule"])]), stGrid]);
  var card = el("section", {"class": "machine" + (a && a.basis_cents != null ? "" : " nobasis"), "data-id": m.id}, [
    el("h2", {text: m.display_name || m.id}),
    el("p", {"class": "basis", text: a && a.basis_cents != null ? "Depreciable basis " + money(a.basis_cents) + ", " + a.federal.method_label : "No basis yet"}),
    form, more, stSet]);
  if (a && a.federal) { card.appendChild(el("h3", {text: "Federal schedule"})); card.appendChild(scheduleTable(a.federal)); }
  if (a && a.state) { card.appendChild(el("h3", {text: a.state.name + " schedule, " + a.state.method_label})); card.appendChild(scheduleTable(a.state)); }
  if (a && a.disposal) {
    var d = a.disposal;
    card.appendChild(el("p", {text: "Disposed of " + d.date + " for " + money(d.price_cents) + ". Adjusted basis " + money(d.adjusted_basis_cents) +
      ", " + (d.gain_cents >= 0 ? "gain " : "loss ") + money(Math.abs(d.gain_cents)) + ", of which " + money(d.recapture_1245_cents) + " is depreciation recapture."}));
  }
  if (a && a.flags.length) { card.appendChild(el("ul", {"class": "flags"}, a.flags.map(function (f) { return el("li", {text: f}); }))); }
  return card;
}
function cents(v, what) {
  v = String(v).trim().replace(/[$,]/g, ""); if (v === "") { return null; }
  if (!/^\d+(\.\d{1,2})?$/.test(v)) { throw new Error(what + ": enter dollars like 1234.56"); }
  return Math.round(Number(v) * 100);
}
function bp(v, what) {
  v = String(v).trim().replace("%", ""); if (v === "") { return null; }
  var n = Number(v); if (!(n >= 0 && n <= 100)) { throw new Error(what + ": enter a percent from 0 to 100"); }
  return Math.round(n * 100);
}
function int(v, what) { v = String(v).trim(); if (v === "") { return null; } if (!/^\d+$/.test(v)) { throw new Error(what + ": whole number"); } return Number(v); }
function years(text, conv, what) {
  var out = {}, any = false;
  String(text).split(/[\n,]+/).forEach(function (line) {
    line = line.trim(); if (!line) { return; }
    var m = /^(\d{4})\s*[:=]\s*(.+)$/.exec(line); if (!m) { throw new Error(what + ": write one year per line, like 2026: 90"); }
    out[m[1]] = conv(m[2], what + " " + m[1]); any = true;
  });
  return any ? out : null;
}
function setOrDrop(o, k, v) { if (v === null || v === "" || v === undefined) { delete o[k]; } else { o[k] = v; } }
function collect() {
  return DATA.machines.map(function (m) {
    var card = document.querySelector('section.machine[data-id="' + m.id + '"]');
    if (!card) { return m; }
    var name = m.display_name || m.id, o = Object.assign({}, m), q = function (n) { return card.querySelector("[name=" + n + "]"); };
    o.depreciation_method = q("depreciation_method").value; o.in_service = q("in_service").value.trim();
    setOrDrop(o, "class", q("class").value); setOrDrop(o, "convention", q("convention").value);
    setOrDrop(o, "purchase_cents", cents(q("purchase_cents").value, name + " purchase price"));
    setOrDrop(o, "section179_cents", cents(q("section179_cents").value, name + " Section 179"));
    setOrDrop(o, "bonus_bp", bp(q("bonus_bp").value, name + " bonus"));
    setOrDrop(o, "life_months", int(q("life_months").value, name + " life"));
    setOrDrop(o, "salvage_cents", cents(q("salvage_cents").value, name + " salvage"));
    setOrDrop(o, "disposed_on", q("disposed_on").value.trim());
    setOrDrop(o, "disposal_price_cents", cents(q("disposal_price_cents").value, name + " sale price"));
    setOrDrop(o, "business_use_bp", years(q("business_use_bp").value, bp, name + " business use"));
    setOrDrop(o, "manual_schedule_cents", years(q("manual_schedule_cents").value, cents, name + " manual schedule"));
    if (q("state_on").checked) {
      var s = {name: q("state_name").value.trim() || "State"};
      setOrDrop(s, "method", q("state_method").value);
      setOrDrop(s, "section179_cents", cents(q("state_section179_cents").value, name + " state Section 179"));
      setOrDrop(s, "bonus_bp", bp(q("state_bonus_bp").value, name + " state bonus"));
      setOrDrop(s, "life_months", int(q("state_life_months").value, name + " state life"));
      o.state = s;
    } else { delete o.state; }
    return o;
  });
}
function render(d) {
  DATA = d;
  document.getElementById("seeded").hidden = !d.seeded;
  document.getElementById("effective-from").value = d.effective_from;
  var mq = document.getElementById("mq"); mq.textContent = "";
  d.mid_quarter.forEach(function (t) {
    if (t.required) { mq.appendChild(el("p", {"class": "warn", text: (t.q4_bp / 100).toFixed(2) + "% of " + t.year +
      "'s depreciable purchases were placed in service in October to December, over 40%, so the mid-quarter convention applies to that year."})); }
  });
  var box = document.getElementById("machines"); box.textContent = "";
  var byId = {}; d.assets.forEach(function (a) { byId[a.id] = a; });
  var owned = d.machines.filter(function (m) { return m.ownership === "owned"; });
  if (!owned.length) { box.appendChild(el("p", {text: "No owned machines. Mark a machine as owned with a purchase price in Settings, then come back here."})); }
  owned.forEach(function (m) { box.appendChild(machineCard(m, byId[m.id])); });
}
function load() { return fetch("/v1/accounting/depreciation").then(function (r) { return r.json(); }).then(render); }
document.getElementById("dep-form").addEventListener("submit", function (ev) {
  ev.preventDefault();
  var status = document.getElementById("status"); status.className = "";
  var body;
  try { body = {key: "machines", value: collect(), effective_from: document.getElementById("effective-from").value.trim()}; }
  catch (e) { status.className = "err"; status.textContent = e.message; return; }
  status.textContent = "Saving";
  fetch("/v1/accounting/settings", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)})
    .then(function (r) { return r.json().then(function (j) { if (!r.ok) { throw new Error(j.errors ? j.errors.join("; ") : (j.error || "HTTP " + r.status)); } }); })
    .then(load).then(function () { status.textContent = "Saved. Schedules below are updated."; })
    .catch(function (e) { status.className = "err"; status.textContent = "Not saved: " + e.message; });
});
load().catch(function (e) { document.getElementById("status").textContent = "Could not load: " + e.message; });
</script></body></html>
"""


def page():
    """The full HTML document of /settings/depreciation."""
    return PAGE
