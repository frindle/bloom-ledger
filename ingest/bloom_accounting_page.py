"""The ledger home page as Python-built HTML: no external assets, one inline style block and one inline script.

Bookkeeping view, not tax advice."""


def body_html():
    """The page <main> markup as a string."""
    return (
        '<main>\n'
        '  <div class="top">\n'
        '    <h1>Ledger</h1>\n'
        '    <nav aria-label="Pages"><a href="/log">Log</a> <a href="/settings">Settings</a></nav>\n'
        '  </div>\n'
        '  <p id="banner" class="banner" role="alert" hidden>Can\'t reach the ledger. Showing nothing until it answers.</p>\n'
        '  <section class="alerts" aria-labelledby="alerts-h"><h2 id="alerts-h">Alerts</h2><ul id="alerts"></ul></section>\n'
        '  <div class="picker">\n'
        '    <label for="period">Period</label>\n'
        '    <select id="period"><option value="day">Today</option><option value="week">This week</option><option value="month" selected>This month</option><option value="quarter">This quarter</option><option value="ytd">Year to date</option><option value="last_year">Last year</option></select>\n'
        '    <label for="machine">Machine</label>\n'
        '    <select id="machine"><option value="">All machines</option></select>\n'
        '  </div>\n'
        '  <section aria-labelledby="sum-h"><h2 id="sum-h">Summary</h2><dl id="summary" class="figures"></dl><p id="power-note" class="meta"></p></section>\n'
        '  <section aria-labelledby="days-h"><h2 id="days-h">Days</h2>\n'
        '    <table><caption>Earnings and power by day, newest first</caption>\n'
        '      <thead><tr><th scope="col">Date</th><th scope="col" class="num">Earned</th><th scope="col" class="num">Sandbox</th><th scope="col" class="num">Energy (kWh)</th><th scope="col" class="num">Hours</th><th scope="col" class="num">Tokens</th></tr></thead>\n'
        '      <tbody id="day-rows"></tbody></table>\n'
        '  </section>\n'
        '  <section aria-labelledby="entries-h"><h2 id="entries-h">Entries</h2>\n'
        '    <table><caption>Manual entries for the period; voided entries are marked</caption>\n'
        '      <thead><tr><th scope="col">Date</th><th scope="col">Kind</th><th scope="col">Category</th><th scope="col" class="num">Amount</th><th scope="col">Machine</th><th scope="col">Note</th><th scope="col">Status</th></tr></thead>\n'
        '      <tbody id="entry-rows"></tbody></table>\n'
        '  </section>\n'
        '</main>\n'
    )



def render_page():
    """The complete home page as one HTML string."""
    return (
        '<!doctype html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '  <title>Ledger</title>\n'
        '  ' + style_block() + '\n'
        '</head>\n'
        '<body>\n'
        '  ' + body_html() + '\n'
        '  <script>' + script_js() + '</script>\n'
        '</body>\n'
        '</html>'
    )


def tokens_format_js():
    """Return JS source defining fmtTokensFull and fmtTokensCompact."""
    return (
        "function fmtTokensFull(n) {\n"
        '  if (typeof n !== "number" || !isFinite(n) || n < 0 || isNaN(n)) return "0";\n'
        "  var s = String(Math.floor(n));\n"
        '  return s.replace(/\\B(?=(\\d{3})+(?!\\d))/g, ",");\n'
        "}\n"
        "function fmtTokensCompact(n) {\n"
        '  if (typeof n !== "number" || !isFinite(n) || n < 0 || isNaN(n)) return "0";\n'
        '  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";\n'
        "  return fmtTokensFull(n);\n"
        "}\n"
    )


def kwh_format_js():
    """Return JS source for the fmtKwh formatter used in the inline script."""
    return """function fmtKwh(n) {
  if (typeof n !== "number" || isNaN(n) || !isFinite(n) || n < 0) return "0.0";
  return n.toFixed(1);
}
""".strip() + '\n'


def script_js():
    """The inline JavaScript that fetches summary data and shows the banner when unreachable."""
    return tokens_format_js() + kwh_format_js() + """(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  function render(s) {
    const t = s.totals;
    const dl = $("summary");
    function figure(label, value, note, title) {
      const d = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = label;
      d.appendChild(dt);
      const dd = document.createElement("dd");
      if (value === null) {
        dd.className = "notset";
        const txt = document.createTextNode("not set ");
        dd.appendChild(txt);
        const a = document.createElement("a");
        a.href = "/settings";
        a.textContent = "Set in Settings";
        dd.appendChild(a);
      } else {
        dd.textContent = value;
      }
      if (title) {
        dd.setAttribute("title", title);
      }
      d.appendChild(dd);
      if (note !== undefined && note !== null) {
        const p = document.createElement("p");
        p.className = "meta";
        p.textContent = note;
        d.appendChild(p);
      }
      return d;
    }
    const earned = "$" + (t.earned_micro / 1e6).toFixed(2);
    const cost = t.cost_micro !== null ? "$" + (t.cost_micro / 1e6).toFixed(2) : null;
    const power_note = "cost " + (cost || "not set");
    const power_val = t.minutes ? fmtKwh(t.kwh) + " kWh" : null;
    const paid_note = "of " + t.total_hours + " h, " + (t.business_bp !== null ? (t.business_bp / 100) + "% paid" : "not set");
    const paid_val = t.minutes ? t.paid_hours + " h" : null;
    const tokens_val = fmtTokensCompact(t.tokens);
    const net_val = s.net_micro !== null ? "$" + (s.net_micro / 1e6).toFixed(2) : null;
    dl.replaceChildren(
      figure("Earned from jobs", earned),
      figure("of which Sandbox", "$" + ((t.sandbox_micro || 0) / 1e6).toFixed(2), "GPU $" + ((t.earned_micro - (t.sandbox_micro || 0)) / 1e6).toFixed(2)),
      figure("Sandbox power", "$" + ((t.sandbox_cost_micro || 0) / 1e6).toFixed(2), (t.sandbox_minutes || 0) + " paid min"),
      figure("Power", power_val, power_note),
      figure("Paid hours", paid_val, paid_note),
      figure("Tokens", tokens_val, null, fmtTokensFull(t.tokens)),
      figure("Net", net_val)
    );
    const dayRows = $("day-rows");
    if (dayRows) {
      const rows = [];
      for (const d of s.days) {
        const tr = document.createElement("tr");
        const th = document.createElement("th");
        th.textContent = d.date;
        tr.appendChild(th);
        const td1 = document.createElement("td");
        td1.className = "num";
        td1.textContent = "$" + (d.earned_micro / 1e6).toFixed(2);
        tr.appendChild(td1);
        const tdS = document.createElement("td");
        tdS.className = "num";
        tdS.textContent = "$" + ((d.sandbox_micro || 0) / 1e6).toFixed(2);
        tr.appendChild(tdS);
        const td2 = document.createElement("td");
        td2.className = "num";
        td2.textContent = fmtKwh(d.wh / 1000);
        tr.appendChild(td2);
        const td3 = document.createElement("td");
        td3.className = "num";
        td3.textContent = (d.minutes / 60).toFixed(2);
        tr.appendChild(td3);
        const td4 = document.createElement("td");
        td4.className = "num";
        td4.textContent = fmtTokensFull(d.tokens);
        tr.appendChild(td4);
        rows.push(tr);
      }
      dayRows.replaceChildren(...rows);
    }
    const entryRows = $("entry-rows");
    if (entryRows) {
      const entries = [];
      for (const e of s.entries.slice().reverse()) {
        const tr = document.createElement("tr");
        const td1 = document.createElement("td");
        td1.textContent = e.date;
        tr.appendChild(td1);
        const td2 = document.createElement("td");
        td2.textContent = e.kind;
        tr.appendChild(td2);
        const td3 = document.createElement("td");
        td3.textContent = e.category;
        tr.appendChild(td3);
        const td4 = document.createElement("td");
        td4.className = "num";
        td4.textContent = "$" + (e.amount_cents / 100).toFixed(2);
        tr.appendChild(td4);
        const td5 = document.createElement("td");
        td5.textContent = e.machine_id !== null ? e.machine_id : "All";
        tr.appendChild(td5);
        const td6 = document.createElement("td");
        td6.textContent = e.note || "";
        tr.appendChild(td6);
        const td7 = document.createElement("td");
        td7.textContent = e.voided ? "Voided" : "Active";
        tr.appendChild(td7);
        if (e.voided) {
          tr.className = "voided";
        }
        entries.push(tr);
      }
      entryRows.replaceChildren(...entries);
    }
    const pwr = s.power || {};
    const pn = $("power-note");
    if (pn) {
      let prefix;
      if (pwr.basis === "metered") {
        prefix = "Power is metered";
      } else if (pwr.estimated) {
        prefix = "Power is estimated from watts";
      } else {
        prefix = "No power readings in this period";
      }
      pn.textContent = prefix + "; " + (pwr.note || "") + ".";
    }
  }
  async function load() {
    const period = $("period").value || "month";
    let url = "/v1/accounting/summary?period=" + encodeURIComponent(period);
    const machine = $("machine");
    if (machine && machine.value) {
      url += "&machine=" + encodeURIComponent(machine.value);
    }
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (r.ok) {
        render(await r.json());
        $("banner").hidden = true;
      } else {
        $("banner").hidden = false;
      }
    } catch (e) {
      $("banner").hidden = false;
    }
  }
  load();
  async function loadAlerts() {
    try {
      const r = await fetch("/v1/alerts", { cache: "no-store" });
      if (!r.ok) return;
      const alerts = (await r.json()) || [];
      const ul = $("alerts");
      if (!ul) return;
      ul.replaceChildren();
      if (alerts.length === 0) {
        const li = document.createElement("li");
        li.textContent = "No open alerts.";
        ul.appendChild(li);
      } else {
        for (const a of alerts) {
          const li = document.createElement("li");
          if (a.alert === "machine-silent") {
            li.textContent = a.machine_id + " has sent nothing for " + Math.round(a.age_s / 60) + " minutes.";
          } else if (a.alert === "ring-snapshot-stale") {
            li.textContent = a.machine_id + " has an old ring snapshot.";
          } else {
            li.textContent = a.machine_id + ": " + a.alert;
          }
          ul.appendChild(li);
        }
      }
    } catch (e) {}
  }
  loadAlerts();
  async function refreshMachines() {
    try {
      const r = await fetch("/v1/summary", { cache: "no-store" });
      if (!r.ok) return;
      const d = await r.json();
      const machines = (d.machines || []);
      const sel = $("machine");
      if (!sel) return;
      const selected = sel.value;
      sel.replaceChildren();
      const allOpt = document.createElement("option");
      allOpt.setAttribute("value", "");
      allOpt.textContent = "All machines";
      sel.appendChild(allOpt);
      for (const m of machines) {
        const opt = document.createElement("option");
        opt.setAttribute("value", m.id);
        opt.textContent = m.id;
        sel.appendChild(opt);
      }
      sel.value = selected;
    } catch (e) {}
  }
  refreshMachines();
  const period = $("period");
  if (period) {
    period.addEventListener("change", load);
  }
  const machine = $("machine");
  if (machine) {
    machine.addEventListener("change", load);
  }
  setInterval(async () => {
    await load();
    await loadAlerts();
  }, 60000);
})();
""".strip() + '\n'
def style_block():
    """The page's inline <style> block as a string."""
    return (
        '<style>\n'
        '  :root { --paper: #e9efec; --card: #f6f9f7; --ink: #12211d; --muted: #4d625b; --rule: #a9bbb4; --bad: #9b2c2c; --warn: #b7791f;\n'
        '          --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Charter, Georgia, serif; }\n'
        '  * { box-sizing: border-box; }\n'
        '  body { margin: 0; background: var(--paper); color: var(--ink); font: 16px/1.5 var(--serif); }\n'
        '  main { max-width: 64rem; margin: 0 auto; padding: 2rem 1.25rem 4rem; }\n'
        '  a { color: var(--ink); text-underline-offset: .2em; }\n'
        '  h1 { font-size: 2.1rem; line-height: 1.15; margin: 0; font-weight: 600; }\n'
        '  h2 { font-size: 1.25rem; margin: 0 0 .5rem; font-weight: 600; }\n'
        '  section { margin-top: 2rem; }\n'
        '  .top { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .25rem 1rem; }\n'
        '  .top nav a { display: inline-block; padding: .35rem .5rem; }\n'
        '  .meta { color: var(--muted); font-size: .9rem; }\n'
        '  .banner { margin: 1rem 0 0; padding: .7rem 1rem; border-left: 4px solid var(--bad); background: #f3dede; }\n'
        '  .banner[hidden] { display: none; }\n'
        '  .picker { display: flex; flex-wrap: wrap; align-items: baseline; gap: .5rem 1rem; margin-top: 1rem; }\n'
        '  .picker select { font: inherit; background: var(--card); color: var(--ink); border: 2px solid var(--ink); border-radius: 0; padding: .3rem .6rem; min-height: 2.75rem; }\n'
        '  dl.figures { display: grid; grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); gap: .75rem; margin: 0; }\n'
        '  dl.figures div { background: var(--card); padding: .6rem .9rem; border-top: 3px solid var(--ink); }\n'
        '  dl.figures dt { color: var(--muted); font-size: .85rem; } dl.figures dd { margin: 0; font-size: 1.3rem; font-variant-numeric: tabular-nums; }\n'
        '  table { width: 100%; border-collapse: collapse; background: var(--card); font-variant-numeric: tabular-nums; }\n'
        '  caption { text-align: left; padding: .5rem .75rem; color: var(--muted); font-size: .9rem; }\n'
        '  th, td { text-align: left; padding: .5rem .75rem; border-bottom: 1px solid var(--rule); font-weight: 400; }\n'
        '  thead th { font-size: .8rem; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); border-bottom-color: var(--ink); }\n'
        '  td.num, th.num { text-align: right; }\n'
        '  tr.voided td { color: var(--muted); text-decoration: line-through; }\n'
        '  .notset { color: var(--bad); }\n'
        '  a:focus-visible, select:focus-visible { outline: 3px solid var(--ink); outline-offset: 2px; }\n'
        '  @media (max-width: 40rem) { main { padding: 1.25rem .75rem 3rem; } th, td { padding: .4rem .5rem; } table { font-size: .9rem; } }\n'
        '  @media (prefers-reduced-motion: no-preference) { .picker select { transition: background .12s; } }\n'
        '</style>\n'
    )
