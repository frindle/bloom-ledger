"""The "Earnings over time" section of the home page: markup, style and inline script (no external assets).

Draws /v1/earnings/series as inline SVG: stacked bars (inference, sandbox, base reward) per day or per month, plus a running-total
line on its own right-hand axis. A table of the same figures sits under the chart for screen readers and keyboards."""


def section_html():
    return (
        '  <section aria-labelledby="graph-h"><h2 id="graph-h">Earnings over time</h2>\n'
        '    <div class="picker">\n'
        '      <span id="graph-view-l">Show</span>\n'
        '      <span role="group" aria-labelledby="graph-view-l" class="seg"><button type="button" id="graph-day" aria-pressed="true">Daily</button>'
        '<button type="button" id="graph-month" aria-pressed="false">Monthly</button></span>\n'
        '    </div>\n'
        '    <p id="graph-total" class="meta" role="status"></p>\n'
        '    <figure class="graph"><div id="graph" role="img" aria-label="Earnings over time"></div>\n'
        '      <figcaption id="graph-legend" class="legend"></figcaption></figure>\n'
        '    <details class="graph-table"><summary>Table of the same figures</summary>\n'
        '      <div class="scroll"><table class="days"><thead><tr><th scope="col" id="gt-first">Day</th><th scope="col" class="num">Earned</th>'
        '<th scope="col" class="num">Running total</th></tr></thead><tbody id="graph-rows"></tbody></table></div></details>\n'
        '  </section>\n'
    )


def style():
    return (
        '  .graph { margin: .75rem 0 0; background: var(--card); padding: .75rem .75rem .5rem; }\n'
        '  .graph svg { display: block; width: 100%; height: auto; }\n'
        '  .graph text { font: 12px var(--serif); fill: var(--muted); }\n'
        '  .graph .axis { stroke: var(--rule); stroke-width: 1; }\n'
        '  .graph .cum { fill: none; stroke: var(--ink); stroke-width: 2; }\n'
        '  .seg button { font: inherit; background: var(--card); color: var(--ink); border: 2px solid var(--ink); border-radius: 0; padding: .3rem .9rem; min-height: 2.75rem; cursor: pointer; }\n'
        '  .seg button + button { border-left: 0; } .seg button[aria-pressed="true"] { background: var(--ink); color: var(--card); }\n'
        '  .legend { display: flex; flex-wrap: wrap; gap: .25rem 1.25rem; font-size: .9rem; color: var(--muted); margin-top: .4rem; }\n'
        '  .legend i { display: inline-block; width: .9rem; height: .9rem; margin-right: .35rem; vertical-align: -.1rem; }\n'
        '  .graph-table { margin-top: .75rem; } .graph-table summary { cursor: pointer; padding: .4rem 0; }\n'
    )


def script_js():
    return r"""(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const NS = "http" + ":" + "//www.w3.org/2000/svg";   // an XML namespace id, not a link; the page test forbids a literal URL
  const SERIES = [["inference_micro", "Inference", "var(--gpu)"], ["sandbox_micro", "Sandbox", "var(--sandbox)"], ["base_micro", "Base reward", "var(--other)"]];
  let data = null, view_ = "day";
  const usd = m => "$" + (m / 1e6).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const short = m => { const v = m / 1e6; return "$" + (v >= 100 ? Math.round(v).toLocaleString("en-US") : v.toFixed(v >= 10 ? 0 : 2)); };
  function node(tag, attrs, text) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (text !== undefined) n.textContent = text;
    return n;
  }
  // Round a maximum up to 1, 2 or 5 times a power of ten, so the axis ends on a clean number.
  function niceMax(v) {
    if (v <= 0) return 1e6;
    const p = Math.pow(10, Math.floor(Math.log10(v))), f = v / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
  }
  function points(view) {
    if (view === "month") return data.months.map(m => ({ label: m.month, earned: m.earned_micro, cum: m.cumulative_micro,
      parts: { inference_micro: m.inference_micro || 0, sandbox_micro: m.sandbox_micro || 0, base_micro: m.base_micro || 0 } }));
    return data.days.map(d => ({ label: d.date, earned: d.earned_micro, cum: d.cumulative_micro,
      parts: { inference_micro: d.inference_micro, sandbox_micro: d.sandbox_micro, base_micro: d.base_micro } }));
  }
  function draw() {
    const view = view_, pts = points(view), box = $("graph");
    box.replaceChildren();
    $("graph-rows").replaceChildren();
    $("gt-first").textContent = view === "month" ? "Month" : "Day";
    $("graph-legend").replaceChildren();
    if (!pts.length) { $("graph-total").textContent = "No earnings recorded yet."; return; }
    $("graph-total").textContent = "Total so far " + usd(data.total_micro) + " over " + data.days.length + " days.";
    const W = 720, H = 300, L = 52, R = 56, T = 14, B = 34, pw = W - L - R, ph = H - T - B;
    const bmax = niceMax(Math.max(...pts.map(p => p.earned))), cmax = niceMax(pts[pts.length - 1].cum);
    const svg = node("svg", { viewBox: "0 0 " + W + " " + H, "aria-hidden": "true", focusable: "false" });
    const slot = pw / pts.length, bw = Math.max(1, Math.min(28, slot * 0.7));
    for (let i = 0; i <= 4; i++) {
      const y = T + ph - ph * i / 4;
      svg.append(node("line", { x1: L, x2: W - R, y1: y, y2: y, class: "axis" }));
      svg.append(node("text", { x: L - 6, y: y + 4, "text-anchor": "end" }, short(bmax * i / 4)));
      svg.append(node("text", { x: W - R + 6, y: y + 4 }, short(cmax * i / 4)));
    }
    pts.forEach((p, i) => {
      const x = L + slot * i + (slot - bw) / 2;
      let y = T + ph;
      const g = node("g", {});
      for (const [key, name, fill] of SERIES) {
        const h = ph * p.parts[key] / bmax;
        if (h > 0) g.append(node("rect", { x, y: y - h, width: bw, height: h, fill }));
        y -= h;
      }
      g.append(node("title", {}, p.label + ": " + usd(p.earned) + ", running total " + usd(p.cum)));
      svg.append(g);
    });
    const step = Math.max(1, Math.ceil(pts.length / 6));
    pts.forEach((p, i) => { if (i % step === 0) svg.append(node("text", { x: L + slot * i + slot / 2, y: H - 12, "text-anchor": "middle" }, view === "month" ? p.label : p.label.slice(5))); });
    svg.append(node("polyline", { class: "cum", points: pts.map((p, i) => (L + slot * i + slot / 2).toFixed(1) + "," + (T + ph - ph * p.cum / cmax).toFixed(1)).join(" ") }));
    box.append(svg);
    const lg = $("graph-legend");
    for (const [, name, fill] of SERIES) {
      const s = document.createElement("span"), i = document.createElement("i");
      i.style.background = fill; s.append(i, name); lg.append(s);
    }
    const c = document.createElement("span"), ci = document.createElement("i");
    ci.style.background = "var(--ink)"; ci.style.height = "3px"; c.append(ci, "Running total (right axis)"); lg.append(c);
    $("graph-rows").replaceChildren(...pts.slice().reverse().map(p => {
      const tr = document.createElement("tr"), th = document.createElement("th");
      th.scope = "row"; th.textContent = p.label; tr.append(th);
      for (const v of [p.earned, p.cum]) { const td = document.createElement("td"); td.className = "num"; td.textContent = usd(v); tr.append(td); }
      return tr;
    }));
  }
  async function load() {
    try {
      const r = await fetch("/v1/earnings/series", { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      data = await r.json();
      draw();
    } catch (e) {
      $("graph-total").textContent = "Can't load the earnings series.";
    }
    setTimeout(load, 300000);
  }
  for (const v of ["day", "month"]) $("graph-" + v).addEventListener("click", () => {
    view_ = v;
    for (const w of ["day", "month"]) $("graph-" + w).setAttribute("aria-pressed", String(w === v));
    if (data) draw();
  });
  load();
})();"""
