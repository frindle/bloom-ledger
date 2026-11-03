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
        '  <div class="picker">\n'
        '    <label for="period">Period</label>\n'
        '    <select id="period"><option value="day">Today</option><option value="week">This week</option><option value="month" selected>This month</option><option value="quarter">This quarter</option><option value="ytd">Year to date</option><option value="last_year">Last year</option></select>\n'
        '    <label for="machine">Machine</label>\n'
        '    <select id="machine"><option value="">All machines</option></select>\n'
        '  </div>\n'
        '  <section aria-labelledby="streams-h"><h2 id="streams-h">What each kind of work paid</h2>\n'
        '    <div id="streams" class="streams"></div>\n'
        '    <p class="meta">Power while working is the metered cost of the minutes that stream was running a job. Idle minutes and your own work are counted below, in the whole machine.</p>\n'
        '  </section>\n'
        '  <section aria-labelledby="sum-h"><h2 id="sum-h">Whole machine</h2><dl id="summary" class="figures"></dl><p id="power-note" class="meta"></p></section>\n'
        '  <section aria-labelledby="days-h"><h2 id="days-h">Days</h2>\n'
        '    <div class="scroll"><table class="days"><caption>Newest first. Open a day to see its minutes and every payment.</caption>\n'
        '      <thead><tr><th scope="col">Date</th><th scope="col" class="num">GPU</th><th scope="col" class="num">Sandbox</th><th scope="col" class="num">Power</th><th scope="col" class="num">Energy (kWh)</th><th scope="col" class="num">Paid h</th><th scope="col" class="num">Hours</th><th scope="col" class="num">Tokens</th></tr></thead>\n'
        '      <tbody id="day-rows"></tbody></table></div>\n'
        '  </section>\n'
        '  <section aria-labelledby="entries-h"><h2 id="entries-h">Entries</h2>\n'
        '    <div class="scroll"><table><caption>Manual entries for the period; voided entries are marked</caption>\n'
        '      <thead><tr><th scope="col">Date</th><th scope="col">Kind</th><th scope="col">Category</th><th scope="col" class="num">Amount</th><th scope="col">Machine</th><th scope="col">Note</th><th scope="col">Status</th></tr></thead>\n'
        '      <tbody id="entry-rows"></tbody></table></div>\n'
        '  </section>\n'
        '  <section class="alerts" aria-labelledby="alerts-h"><h2 id="alerts-h">Alerts</h2><ul id="alerts"></ul></section>\n'
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
    """The inline JavaScript: fetches the summary, draws both streams and the days, and opens a day's logs on request."""
    return tokens_format_js() + kwh_format_js() + """(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const NAMES = { gpu: "Darkbloom GPU", sandbox: "Sandbox", other: "Your own work", idle: "Idle", gap: "No reading" };
  const COLS = 8;
  let last = null;
  const open = new Set();
  const details = new Map();
  const showAll = new Set();
  function usd(micro) {
    const v = Math.abs(micro) / 1e6;
    return (micro < 0 ? "\\u2212$" : "$") + v.toFixed(2);
  }
  function usdFine(micro) {
    if (micro !== 0 && Math.abs(micro) < 10000) return "$" + (micro / 1e6).toFixed(6).replace(/(\\.\\d{4}\\d*?)0+$/, "$1");
    return usd(micro);
  }
  function el(tag, text, cls) {
    const e = document.createElement(tag);
    if (text !== undefined && text !== null) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  }
  function notSet() {
    const span = el("span", "not set ", "notset");
    const a = el("a", "Set in Settings");
    a.href = "/settings";
    span.appendChild(a);
    return span;
  }
  function figure(label, value, note, title) {
    const d = document.createElement("div");
    d.appendChild(el("dt", label));
    const dd = document.createElement("dd");
    if (value === null) {
      dd.className = "notset";
      dd.appendChild(document.createTextNode("not set "));
      const a = el("a", "Set in Settings");
      a.href = "/settings";
      dd.appendChild(a);
    } else {
      dd.textContent = value;
    }
    if (title) dd.setAttribute("title", title);
    d.appendChild(dd);
    if (note !== undefined && note !== null) d.appendChild(el("p", note, "meta"));
    return d;
  }
  function sumLine(label, value, cls) {
    const row = el("div", null, cls || "line");
    row.appendChild(el("dt", label));
    const dd = el("dd");
    if (value === null) dd.appendChild(notSet()); else dd.textContent = value;
    row.appendChild(dd);
    return row;
  }
  function stream(key, earned, cost, minutes, extra, costKnown) {
    const art = el("article", null, "stream s-" + key);
    art.appendChild(el("h3", NAMES[key]));
    const dl = el("dl", null, "sum");
    dl.appendChild(sumLine("Earned", usd(earned)));
    dl.appendChild(sumLine("Power while working", costKnown ? usd(-cost) : null));
    dl.appendChild(sumLine("Margin over power", costKnown ? usd(earned - cost) : null, "line total"));
    art.appendChild(dl);
    const h = (minutes / 60).toFixed(minutes < 600 ? 2 : 1);
    art.appendChild(el("p", minutes + " paid minutes (" + h + " h)" + (extra ? ", " + extra : ""), "meta"));
    return art;
  }
  function render(s) {
    last = s;
    const t = s.totals;
    const costKnown = t.cost_micro !== null && t.cost_micro !== undefined;
    const gpuEarned = t.gpu_micro !== undefined ? t.gpu_micro : t.earned_micro - (t.sandbox_micro || 0);
    const box = $("streams");
    if (box) {
      box.replaceChildren(
        stream("gpu", gpuEarned, t.gpu_cost_micro || 0, t.gpu_minutes || 0, fmtTokensCompact(t.tokens) + " tokens", costKnown),
        stream("sandbox", t.sandbox_micro || 0, t.sandbox_cost_micro || 0, t.sandbox_minutes || 0, null, costKnown)
      );
    }
    const cost = costKnown ? usd(t.cost_micro) : null;
    const power_note = "cost " + (cost || "not set");
    const power_val = t.minutes ? fmtKwh(t.kwh) + " kWh" : null;
    const paid_note = "of " + t.total_hours + " h, " + (t.business_bp !== null ? (t.business_bp / 100) + "% paid" : "not set");
    const paid_val = t.minutes ? t.paid_hours + " h" : null;
    const net_val = s.net_micro !== null ? usd(s.net_micro) : null;
    const own = t.other_minutes ? (t.other_minutes / 60).toFixed(1) + " h your own work" : null;
    const net = figure("Net", net_val, "after all power, lease and depreciation");
    net.className = "net";
    $("summary").replaceChildren(
      figure("Earned", usd(t.earned_micro)),
      figure("Power", power_val, power_note),
      figure("Paid hours", paid_val, own ? paid_note + "; " + own : paid_note),
      figure("Tokens", fmtTokensCompact(t.tokens), null, fmtTokensFull(t.tokens)),
      net
    );
    drawDays();
    const entryRows = $("entry-rows");
    if (entryRows) {
      const entries = [];
      for (const e of s.entries.slice().reverse()) {
        const tr = document.createElement("tr");
        tr.appendChild(el("td", e.date));
        tr.appendChild(el("td", e.kind));
        tr.appendChild(el("td", e.category));
        tr.appendChild(el("td", "$" + (e.amount_cents / 100).toFixed(2), "num"));
        tr.appendChild(el("td", e.machine_id !== null ? e.machine_id : "All"));
        tr.appendChild(el("td", e.note || ""));
        tr.appendChild(el("td", e.voided ? "Voided" : "Active"));
        if (e.voided) tr.className = "voided";
        entries.push(tr);
      }
      entryRows.replaceChildren(...entries);
    }
    const pwr = s.power || {};
    const pn = $("power-note");
    if (pn) {
      let prefix;
      if (pwr.basis === "metered") prefix = "Power is metered";
      else if (pwr.estimated) prefix = "Power is estimated from watts";
      else prefix = "No power readings in this period";
      pn.textContent = prefix + "; " + (pwr.note || "") + ".";
    }
  }
  function dayRow(d) {
    const tr = el("tr", null, open.has(d.date) ? "day open" : "day");
    const th = el("th");
    th.setAttribute("scope", "row");
    const b = el("button", d.date, "toggle");
    b.type = "button";
    b.setAttribute("aria-expanded", open.has(d.date) ? "true" : "false");
    b.setAttribute("aria-controls", "day-" + d.date);
    b.addEventListener("click", () => toggleDay(d.date));
    th.appendChild(b);
    tr.appendChild(th);
    const gpu = d.gpu_micro !== undefined ? d.gpu_micro : d.earned_micro - (d.sandbox_micro || 0);
    tr.appendChild(el("td", usd(gpu), "num"));
    tr.appendChild(el("td", usd(d.sandbox_micro || 0), "num"));
    tr.appendChild(el("td", d.cost_micro === null || d.cost_micro === undefined ? "\\u2013" : usd(d.cost_micro), "num"));
    tr.appendChild(el("td", fmtKwh(d.wh / 1000), "num"));
    tr.appendChild(el("td", ((d.paid_minutes || 0) / 60).toFixed(2), "num"));
    tr.appendChild(el("td", (d.minutes / 60).toFixed(2), "num"));
    tr.appendChild(el("td", fmtTokensFull(d.tokens), "num"));
    return tr;
  }
  function drawDays() {
    const body = $("day-rows");
    if (!body || !last) return;
    const rows = [];
    for (const d of last.days) {
      rows.push(dayRow(d));
      if (open.has(d.date)) {
        const tr = el("tr", null, "detail");
        tr.id = "day-" + d.date;
        const td = el("td");
        td.setAttribute("colspan", String(COLS));
        td.appendChild(detailView(d.date));
        tr.appendChild(td);
        rows.push(tr);
      }
    }
    body.replaceChildren(...rows);
  }
  async function toggleDay(date) {
    if (open.has(date)) {
      open.delete(date);
      drawDays();
      return;
    }
    open.add(date);
    details.set(date, "loading");
    drawDays();
    let url = "/v1/accounting/day?date=" + encodeURIComponent(date);
    const m = $("machine");
    if (m && m.value) url += "&machine=" + encodeURIComponent(m.value);
    try {
      const r = await fetch(url, { cache: "no-store" });
      details.set(date, r.ok ? await r.json() : "error");
    } catch (e) {
      details.set(date, "error");
    }
    drawDays();
  }
  function table(caption, heads, rows) {
    const wrap = el("div", null, "scroll");
    const tb = el("table", null, "inner");
    tb.appendChild(el("caption", caption));
    const thead = el("thead");
    const hr = el("tr");
    for (const h of heads) {
      const th = el("th", h[0], h[1] ? "num" : null);
      th.setAttribute("scope", "col");
      hr.appendChild(th);
    }
    thead.appendChild(hr);
    tb.appendChild(thead);
    const body = el("tbody");
    for (const r of rows) {
      const tr = el("tr");
      r.forEach((v, i) => tr.appendChild(el("td", v, heads[i][1] ? "num" : null)));
      body.appendChild(tr);
    }
    tb.appendChild(body);
    wrap.appendChild(tb);
    return wrap;
  }
  function strip(minutes) {
    const slots = new Array(1440).fill("none");
    const counts = { gpu: 0, sandbox: 0, other: 0, idle: 0, gap: 0 };
    for (const m of minutes) {
      if (m.slot >= 0 && m.slot < 1440) slots[m.slot] = m.stream;
      counts[m.stream] = (counts[m.stream] || 0) + 1;
    }
    const bar = el("div", null, "strip");
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", "Minute by minute: " + Object.keys(counts).map(k => counts[k] + " " + NAMES[k].toLowerCase()).join(", "));
    let i = 0;
    while (i < 1440) {
      let j = i;
      while (j < 1440 && slots[j] === slots[i]) j++;
      const seg = el("span", null, "seg s-" + slots[i]);
      seg.style.flexGrow = String(j - i);
      const hhmm = n => String(Math.floor(n / 60)).padStart(2, "0") + ":" + String(n % 60).padStart(2, "0");
      seg.title = hhmm(i) + "\\u2013" + hhmm(j) + " " + (slots[i] === "none" ? "no data" : NAMES[slots[i]]);
      bar.appendChild(seg);
      i = j;
    }
    const wrap = el("figure", null, "timeline");
    wrap.appendChild(bar);
    const ticks = el("div", null, "ticks");
    for (const h of ["00", "06", "12", "18", "24"]) ticks.appendChild(el("span", h + ":00"));
    wrap.appendChild(ticks);
    const legend = el("ul", null, "legend");
    for (const k of ["gpu", "sandbox", "other", "idle", "gap"]) {
      const li = el("li");
      li.appendChild(el("span", null, "key s-" + k));
      li.appendChild(document.createTextNode(NAMES[k] + " " + counts[k] + " min"));
      legend.appendChild(li);
    }
    wrap.appendChild(legend);
    return wrap;
  }
  function detailView(date) {
    const box = el("div", null, "daydetail");
    const d = details.get(date);
    if (d === "loading" || d === undefined) {
      box.appendChild(el("p", "Loading " + date + "\\u2026", "meta"));
      return box;
    }
    if (d === "error") {
      box.appendChild(el("p", "Couldn't load " + date + ". Close and open the day to try again.", "notset"));
      return box;
    }
    box.appendChild(strip(d.minutes));
    if (d.earnings.length) {
      box.appendChild(table(d.earnings.length + (d.earnings.length === 1 ? " payment" : " payments") + ", local time", [["Time"], ["Stream"], ["Model"], ["Job"], ["Tokens", 1], ["Amount", 1]],
        d.earnings.map(e => [e.time, NAMES[e.stream], e.model, e.job_id, fmtTokensFull(e.tokens), usdFine(e.micro_usd)])));
    } else {
      box.appendChild(el("p", "No payments on " + date + ".", "meta"));
    }
    const hr = h => String(h).padStart(2, "0") + ":00";
    box.appendChild(table("By hour", [["Hour"], ["GPU min", 1], ["Sandbox min", 1], ["Own work min", 1], ["Idle min", 1], ["kWh", 1], ["Power", 1], ["Earned", 1]],
      d.hours.map(h => [hr(h.hour), String(h.gpu), String(h.sandbox), String(h.other), String(h.idle), (h.wh / 1000).toFixed(3),
        h.cost_micro === null ? "\\u2013" : usdFine(h.cost_micro), usdFine(h.earned_micro)])));
    const more = el("button", (showAll.has(date) ? "Hide" : "Show") + " all " + d.minutes.length + " minutes", "more");
    more.type = "button";
    more.setAttribute("aria-expanded", showAll.has(date) ? "true" : "false");
    more.addEventListener("click", () => {
      if (showAll.has(date)) showAll.delete(date); else showAll.add(date);
      drawDays();
    });
    box.appendChild(more);
    if (showAll.has(date)) {
      box.appendChild(table("Every power minute", [["Time"], ["Stream"], ["Darkbloom state"], ["Wh", 1], ["Tokens", 1], ["Sandbox jobs", 1], ["Cost", 1]],
        d.minutes.map(m => [m.time, NAMES[m.stream], m.state, m.wh.toFixed(2), fmtTokensFull(m.tokens), String(m.sandbox_jobs),
          m.cost_micro === null ? "\\u2013" : usdFine(m.cost_micro)])));
    }
    return box;
  }
  async function load() {
    const period = $("period").value || "month";
    let url = "/v1/accounting/summary?period=" + encodeURIComponent(period);
    const machine = $("machine");
    if (machine && machine.value) url += "&machine=" + encodeURIComponent(machine.value);
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
        ul.appendChild(el("li", "No open alerts."));
      } else {
        for (const a of alerts) {
          let txt;
          if (a.alert === "machine-silent") txt = a.machine_id + " has sent nothing for " + Math.round(a.age_s / 60) + " minutes.";
          else if (a.alert === "ring-snapshot-stale") txt = a.machine_id + " has an old ring snapshot.";
          else txt = a.machine_id + ": " + a.alert;
          ul.appendChild(el("li", txt));
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
  if (period) period.addEventListener("change", () => { open.clear(); details.clear(); load(); });
  const machine = $("machine");
  if (machine) machine.addEventListener("change", () => { open.clear(); details.clear(); load(); });
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
        '          --gpu: #2b5f86; --sandbox: #6d4a8f; --other: #c08a2e; --idle: #cbd8d2;\n'
        '          --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Charter, Georgia, serif; }\n'
        '  * { box-sizing: border-box; }\n'
        '  body { margin: 0; background: var(--paper); color: var(--ink); font: 17px/1.55 var(--serif); font-variant-numeric: lining-nums; }\n'
        '  main { max-width: 66rem; margin: 0 auto; padding: 2.25rem 1.25rem 4rem; }\n'
        '  a { color: var(--ink); text-underline-offset: .2em; }\n'
        '  h1 { font-size: 2.4rem; line-height: 1.1; margin: 0; font-weight: 600; letter-spacing: -.01em; }\n'
        '  h2 { font-size: 1.3rem; margin: 0 0 .75rem; font-weight: 600; }\n'
        '  h3 { font-size: 1.15rem; margin: 0 0 .5rem; font-weight: 600; }\n'
        '  section { margin-top: 2.5rem; }\n'
        '  .top { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .25rem 1rem; }\n'
        '  .top nav a { display: inline-block; padding: .35rem .5rem; }\n'
        '  .meta { color: var(--muted); font-size: .9rem; margin: .5rem 0 0; max-width: 42rem; }\n'
        '  .banner { margin: 1rem 0 0; padding: .7rem 1rem; border-left: 4px solid var(--bad); background: #f3dede; }\n'
        '  .banner[hidden] { display: none; }\n'
        '  .picker { display: flex; flex-wrap: wrap; align-items: baseline; gap: .5rem 1rem; margin-top: 1.25rem; }\n'
        '  .picker select { font: inherit; background: var(--card); color: var(--ink); border: 2px solid var(--ink); border-radius: 0; padding: .3rem .6rem; min-height: 2.75rem; }\n'
        # The two stream ledgers: a hand-ruled subtraction, single rule above the margin and a double rule under it.
        '  .streams { display: grid; grid-template-columns: repeat(auto-fit, minmax(19rem, 1fr)); gap: 1.25rem; }\n'
        '  .stream { background: var(--card); padding: 1rem 1.25rem 1.1rem 1.4rem; border-left: 6px solid var(--gpu); }\n'
        '  .stream.s-sandbox { border-left-color: var(--sandbox); }\n'
        '  .stream h3 { color: var(--gpu); } .stream.s-sandbox h3 { color: var(--sandbox); }\n'
        '  dl.sum { margin: 0; font-variant-numeric: tabular-nums; }\n'
        '  dl.sum .line { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; padding: .2rem 0; }\n'
        '  dl.sum dt { color: var(--muted); } dl.sum dd { margin: 0; font-size: 1.15rem; text-align: right; }\n'
        '  dl.sum .total { margin-top: .35rem; padding-top: .45rem; border-top: 1px solid var(--ink); }\n'
        '  dl.sum .total dt { color: var(--ink); }\n'
        '  dl.sum .total dd { font-size: 2rem; line-height: 1.1; font-weight: 600; border-bottom: 4px double var(--ink); padding-bottom: .1rem; }\n'
        '  dl.figures { display: grid; grid-template-columns: repeat(auto-fit, minmax(10.5rem, 1fr)); gap: .75rem; margin: 0; }\n'
        '  dl.figures div { background: var(--card); padding: .6rem .9rem; border-top: 3px solid var(--ink); }\n'
        '  dl.figures dt { color: var(--muted); font-size: .85rem; } dl.figures dd { margin: 0; font-size: 1.3rem; font-variant-numeric: tabular-nums; }\n'
        '  dl.figures .net dd { display: inline-block; font-weight: 600; border-bottom: 4px double var(--ink); }\n'
        '  .scroll { overflow-x: auto; }\n'
        '  table { width: 100%; border-collapse: collapse; background: var(--card); font-variant-numeric: tabular-nums; }\n'
        '  caption { text-align: left; padding: .5rem .75rem; color: var(--muted); font-size: .9rem; }\n'
        '  th, td { text-align: left; padding: .5rem .75rem; border-bottom: 1px solid var(--rule); font-weight: 400; white-space: nowrap; }\n'
        '  thead th { font-size: .85rem; color: var(--muted); border-bottom-color: var(--ink); }\n'
        '  td.num, th.num { text-align: right; }\n'
        '  tr.voided td { color: var(--muted); text-decoration: line-through; }\n'
        '  .toggle, .more { font: inherit; color: var(--ink); background: none; border: 0; padding: .25rem .25rem .25rem 0; cursor: pointer; min-height: 2.25rem; }\n'
        '  .toggle::before { content: ""; display: inline-block; width: 0; height: 0; margin-right: .55rem; vertical-align: .08em;\n'
        '                    border-left: .45em solid currentColor; border-top: .3em solid transparent; border-bottom: .3em solid transparent; }\n'
        '  .toggle[aria-expanded="true"]::before { transform: rotate(90deg); }\n'
        '  tr.day.open th, tr.day.open td { border-bottom-color: transparent; background: #edf3f0; }\n'
        '  tr.detail > td { background: #edf3f0; padding: .25rem .75rem 1.25rem; white-space: normal; border-bottom: 2px solid var(--ink); }\n'
        '  .daydetail { display: grid; gap: 1rem; }\n'
        '  .more { text-decoration: underline; text-underline-offset: .2em; justify-self: start; }\n'
        '  table.inner { background: var(--card); font-size: .92rem; } table.inner caption { padding-left: 0; }\n'
        '  .timeline { margin: .5rem 0 0; }\n'
        '  .strip { display: flex; height: 2.5rem; border: 1px solid var(--ink); background: var(--card); }\n'
        '  .seg { flex: 1 1 0; min-width: 0; }\n'
        '  .s-gpu.seg, .key.s-gpu { background: var(--gpu); } .s-sandbox.seg, .key.s-sandbox { background: var(--sandbox); }\n'
        '  .s-other.seg, .key.s-other { background: var(--other); } .s-idle.seg, .key.s-idle { background: var(--idle); }\n'
        '  .s-gap.seg, .key.s-gap, .s-none.seg { background: repeating-linear-gradient(135deg, transparent 0 3px, var(--rule) 3px 4px); }\n'
        '  .ticks { display: flex; justify-content: space-between; color: var(--muted); font-size: .8rem; margin-top: .2rem; font-variant-numeric: tabular-nums; }\n'
        '  .legend { display: flex; flex-wrap: wrap; gap: .25rem 1.25rem; list-style: none; margin: .5rem 0 0; padding: 0; font-size: .9rem; }\n'
        '  .key { display: inline-block; width: .9rem; height: .9rem; margin-right: .4rem; vertical-align: -.1em; border: 1px solid var(--ink); }\n'
        '  .alerts ul { margin: 0; padding-left: 1.2rem; color: var(--muted); }\n'
        '  .notset { color: var(--bad); }\n'
        '  a:focus-visible, select:focus-visible, button:focus-visible { outline: 3px solid var(--ink); outline-offset: 2px; }\n'
        '  @media (max-width: 40rem) { main { padding: 1.25rem .75rem 3rem; } th, td { padding: .4rem .5rem; } table { font-size: .9rem; }\n'
        '    dl.sum .total dd { font-size: 1.6rem; } }\n'
        '  @media (prefers-reduced-motion: no-preference) { .toggle::before { transition: transform .15s ease-out; } .picker select { transition: background .12s; } }\n'
        '</style>\n'
    )
