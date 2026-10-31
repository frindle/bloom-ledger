// Test support (frozen): runs the inline <script> of an HTML page against a tiny fake DOM and prints JSON.
// usage: node dom_harness.js PAGE.html SCENARIO.json
// scenario: {"fetch": {"<path>": {"status": 200, "body": {...}}}, "steps": [{"do": "submit|click|input", "id": "...", "values": {"<id>": "<value>"}}]}
// The page may only use: document.getElementById/createElement/createTextNode/querySelector(All)(#id|.class|tag only),
// element.append/appendChild/replaceChildren/remove/setAttribute/getAttribute/removeAttribute/addEventListener/focus/
// select/closest/classList/dataset/hidden/disabled/value/textContent/type/title/href/id/className, fetch, sessionStorage,
// navigator.clipboard.writeText, setTimeout/setInterval (never fired), JSON, Date, URL, Promise, confirm (not used).
"use strict";
const fs = require("fs"), vm = require("vm");
const [page, scenarioPath] = process.argv.slice(2);
const scenario = JSON.parse(fs.readFileSync(scenarioPath, "utf8"));
const out = { errors: [], inner_html_writes: 0, local_storage_calls: 0, fetches: [], clipboard: [], console: [] };
const byId = new Map();
class El {
  constructor(tag) { this.tag = tag; this.attrs = {}; this.children = []; this.listeners = {}; this.parent = null; this._text = null;
    this.hidden = false; this.disabled = false; this.value = ""; this.dataset = {}; this.style = {};
    const self = this;
    this.classList = { add: c => self._cls(l => l.add(c)), remove: c => self._cls(l => l.delete(c)),
      toggle: (c, f) => self._cls(l => ((f === undefined ? !l.has(c) : f) ? l.add(c) : l.delete(c))), contains: c => self._classes().has(c) }; }
  _classes() { return new Set((this.attrs["class"] || "").split(/\s+/).filter(Boolean)); }
  _cls(fn) { const s = this._classes(); fn(s); this.attrs["class"] = [...s].join(" "); }
  get id() { return this.attrs.id || ""; } set id(v) { this.attrs.id = String(v); if (v) byId.set(String(v), this); }
  get className() { return this.attrs["class"] || ""; } set className(v) { this.attrs["class"] = String(v); }
  get type() { return this.attrs.type || ""; } set type(v) { this.attrs.type = String(v); }
  get title() { return this.attrs.title || ""; } set title(v) { this.attrs.title = String(v); }
  get href() { return this.attrs.href || ""; } set href(v) { this.attrs.href = String(v); }
  get name() { return this.attrs.name || ""; } set name(v) { this.attrs.name = String(v); }
  get textContent() { return this._text !== null && !this.children.length ? this._text : this.children.map(c => c.textContent).join(""); }
  set textContent(v) { this.children = []; this._text = String(v); }
  set innerHTML(v) { out.inner_html_writes += 1; this.children = []; this._text = String(v); }
  get innerHTML() { out.inner_html_writes += 1; return this.textContent; }
  _adopt(k) { if (typeof k === "string") { const t = new El("#text"); t._text = k; k = t; } if (k.parent) k.parent.children = k.parent.children.filter(x => x !== k);
    k.parent = this; this._text = null; return k; }
  append(...ks) { for (const k of ks) this.children.push(this._adopt(k)); }
  appendChild(k) { this.append(k); return k; }
  replaceChildren(...ks) { this.children = []; this._text = null; this.append(...ks); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(x => x !== this); this.parent = null; }
  setAttribute(k, v) { if (k === "hidden") { this.hidden = true; return; } if (k === "disabled") { this.disabled = true; return; }
    if (k === "id") { this.id = v; return; } this.attrs[k] = String(v); }
  getAttribute(k) { return k === "hidden" ? (this.hidden ? "" : null) : k === "disabled" ? (this.disabled ? "" : null) : (k in this.attrs ? this.attrs[k] : null); }
  removeAttribute(k) { if (k === "hidden") this.hidden = false; else if (k === "disabled") this.disabled = false; else delete this.attrs[k]; }
  addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); }
  focus() {} select() {} reset() { this.walk(e => { if (e.tag === "input") e.value = ""; }); }
  closest(sel) { for (let e = this; e; e = e.parent) if (e.matches(sel)) return e; return null; }
  matches(sel) { return sel.startsWith("#") ? this.id === sel.slice(1) : sel.startsWith(".") ? this._classes().has(sel.slice(1)) : this.tag === sel; }
  walk(fn) { fn(this); this.children.forEach(c => c.walk(fn)); }
  querySelectorAll(sel) { const r = []; this.children.forEach(c => c.walk(e => { if (e.matches(sel)) r.push(e); })); return r; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  get elements() { return this.querySelectorAll("input"); }
}
const VOID = new Set(["meta", "link", "input", "br", "hr", "img"]);
function parse(html) {
  const root = new El("body"); let cur = root;
  html = html.replace(/<!--[\s\S]*?-->/g, "").replace(/<(script|style)[\s\S]*?<\/\1>/gi, "");
  const re = /<(\/?)([a-zA-Z][\w-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>|([^<]+)/g; let m;
  while ((m = re.exec(html))) {
    if (m[4] !== undefined) { if (m[4].trim() && cur !== root) { cur.children.push(Object.assign(new El("#text"), { _text: m[4].replace(/\s+/g, " ") })); } continue; }
    const tag = m[2].toLowerCase();
    if (m[1]) { for (let e = cur; e && e !== root; e = e.parent) if (e.tag === tag) { cur = e.parent || root; break; } continue; }
    const el = new El(tag), ar = /([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g; let a;
    while ((a = ar.exec(m[3]))) { const v = a[2] !== undefined ? a[2] : a[3] !== undefined ? a[3] : a[4] !== undefined ? a[4] : "";
      if (a[1] === "hidden") el.hidden = true; else if (a[1] === "disabled") el.disabled = true; else if (a[1] === "value") el.value = v; else el.attrs[a[1]] = v; }
    if (el.attrs.id) byId.set(el.attrs.id, el);
    el.parent = cur; cur.children.push(el); if (!VOID.has(tag) && !/\/\s*$/.test(m[3])) cur = el;
  }
  return root;
}
const html = fs.readFileSync(page, "utf8"), body = parse(html);
const scripts = [...html.matchAll(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/gi)].map(s => s[1]);
const store = () => { const d = {}; return { getItem: k => (k in d ? d[k] : null), setItem: (k, v) => { d[k] = String(v); }, removeItem: k => { delete d[k]; }, _d: d }; };
const session = store();
const doc = { getElementById: id => byId.get(id) || null, createElement: t => new El(t), createTextNode: s => Object.assign(new El("#text"), { _text: String(s) }),
  querySelector: s => body.querySelector(s), querySelectorAll: s => body.querySelectorAll(s), addEventListener() {}, body, documentElement: body,
  get activeElement() { return null; } };
const sandbox = { document: doc, sessionStorage: session, JSON, Date, URL, Promise, Math, Number, String, Object, Array, Set, Map, RegExp, Error, isNaN, parseInt,
  localStorage: new Proxy({}, { get() { out.local_storage_calls += 1; return () => null; }, set() { out.local_storage_calls += 1; return true; } }),
  location: { origin: scenario.origin || "http://10.0.12.46:8787", href: (scenario.origin || "http://10.0.12.46:8787") + "/settings", pathname: "/settings", host: "10.0.12.46:8787", protocol: "http:" },
  navigator: { clipboard: { writeText: s => { out.clipboard.push(String(s)); return Promise.resolve(); } } },
  console: { log: (...a) => out.console.push(a.map(String).join(" ")), error: (...a) => out.console.push(a.map(String).join(" ")), warn: (...a) => out.console.push(a.map(String).join(" ")) },
  setTimeout: () => 0, setInterval: () => 0, clearTimeout() {}, clearInterval() {}, confirm: () => { out.errors.push("confirm() used"); return false; },
  alert: () => { out.errors.push("alert() used"); }, prompt: () => { out.errors.push("prompt() used"); return null; },
  fetch: async (url, opts) => { opts = opts || {}; const h = {}; for (const [k, v] of Object.entries(opts.headers || {})) h[k.toLowerCase()] = v;
    out.fetches.push({ url: String(url), method: opts.method || "GET", headers: h, body: opts.body === undefined ? null : String(opts.body) });
    const r = scenario.fetch[String(url)] || scenario.fetch[(opts.method || "GET") + " " + String(url)];
    if (!r) throw new Error("no fixture for " + url);
    if (r.network_error) throw new Error("network down");
    return { ok: r.status >= 200 && r.status < 300, status: r.status, json: async () => JSON.parse(JSON.stringify(r.body)), text: async () => JSON.stringify(r.body) }; } };
sandbox.window = sandbox; sandbox.globalThis = sandbox;
const ctx = vm.createContext(sandbox);
const flush = async () => { for (let i = 0; i < 20; i++) await new Promise(r => setImmediate(r)); };
const ser = e => ({ tag: e.tag, id: e.id, class: e.className, attrs: e.attrs, hidden: e.hidden, disabled: e.disabled, value: e.value,
  text: e.textContent, children: e.tag === "#text" ? [] : e.children.map(ser) });
(async () => {
  try { for (const s of scripts) vm.runInContext(s, ctx, { timeout: 2000 }); } catch (e) { out.errors.push("script: " + e.message); }
  await flush();
  for (const st of scenario.steps || []) {
    try {
      if (st.do === "call") { if (typeof sandbox[st.fn] !== "function") out.errors.push("no function window." + st.fn); else await sandbox[st.fn](); await flush(); continue; }
      for (const [id, v] of Object.entries(st.values || {})) { const el = byId.get(id); if (el) el.value = v; }
      const el = byId.get(st.id) || (st.sel ? body.querySelector(st.sel) : null);
      if (!el) { out.errors.push("no element " + (st.id || st.sel)); continue; }
      const ev = { type: st.do, target: el, currentTarget: el, key: st.key, preventDefault() {}, stopPropagation() {} };
      for (const fn of (el.listeners[st.do === "input" ? "input" : st.do] || [])) await fn(ev);
      if (st.do === "click") { let p = el.parent; while (p) { for (const fn of (p.listeners.click || [])) await fn(Object.assign({}, ev, { currentTarget: p })); p = p.parent; } }
    } catch (e) { out.errors.push("step: " + e.message); }
    await flush();
  }
  out.session = session._d; out.dom = ser(body);
  process.stdout.write(JSON.stringify(out));
})();
