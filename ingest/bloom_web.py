"""Pages that belong to the shared look: /setup, /login, /status, and the helper that gives the older pages the same theme."""
import json
from pathlib import Path

STATIC = Path(__file__).resolve().parent / "static"
TYPES = {".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8"}
HEAD = '<link rel="stylesheet" href="/static/bloom.css"><script src="/static/bloom-ui.js" defer></script>'
TZ_CHOICES = ["UTC", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Anchorage", "Pacific/Honolulu",
              "America/Toronto", "America/Mexico_City", "America/Sao_Paulo", "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Madrid",
              "Europe/Moscow", "Africa/Johannesburg", "Asia/Dubai", "Asia/Kolkata", "Asia/Singapore", "Asia/Hong_Kong", "Asia/Tokyo",
              "Asia/Seoul", "Australia/Sydney", "Pacific/Auckland"]


def static_file(name):
    """(content_type, bytes) for /static/<name>, or None. Only the two shipped files; no path tricks."""
    if name not in ("bloom.css", "bloom-ui.js"):
        return None
    p = STATIC / name
    return (TYPES[p.suffix], p.read_bytes()) if p.is_file() else None


def themed(html):
    """Add the shared stylesheet and header script to an older page (last in <head>, so the theme wins)."""
    if "/static/bloom.css" in html:
        return html
    i = html.lower().find("</head>")
    return html[:i] + HEAD + html[i:] if i >= 0 else HEAD + html


def shell(title, body, script="", bare=False):
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="color-scheme" content="light dark"><title>%s</title>%s</head><body%s>%s<script>%s</script></body></html>'
            % (title, HEAD, " data-bare" if bare else "", body, script))


COMMON_JS = """
function $(id){return document.getElementById(id);}
function api(method, path, body){
  return fetch(path, {method: method, credentials: "same-origin", headers: body ? {"Content-Type": "application/json"} : {}, body: body ? JSON.stringify(body) : undefined})
    .then(function(r){return r.json().catch(function(){return {};}).then(function(j){return {status: r.status, body: j};});});
}
"""


def login_page():
    body = """<main><div class="bl-narrow"><h1>Log in</h1>
<p class="meta">Log in to change settings. Reading the dashboard does not need a login.</p>
<form id="f" class="bl-panel" autocomplete="on">
<div class="bl-field"><label for="u">Username</label><input id="u" name="username" autocomplete="username" required autofocus></div>
<div class="bl-field"><label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password" required></div>
<p id="err" class="bl-err" role="alert"></p>
<button class="primary" type="submit" id="go">Log in</button>
</form>
<p class="bl-hint">Forgot the password? Run <code>docker compose exec bloom-ledger python3 /app/server.py reset-admin</code> (or <code>python3 server.py reset-admin</code> on a Mac install), then open /setup.</p>
</div></main>"""
    js = COMMON_JS + """
api("GET", "/v1/auth/me").then(function(r){ if (r.body.mode === "setup") location.href = "/setup"; });
$("f").addEventListener("submit", function(e){
  e.preventDefault(); $("err").textContent = ""; $("go").disabled = true;
  api("POST", "/v1/auth/login", {username: $("u").value, password: $("p").value}).then(function(r){
    if (r.status === 200) { location.href = new URLSearchParams(location.search).get("next") || "/"; }
    else { $("err").textContent = r.body.error || "Could not log in."; $("go").disabled = false; }
  }).catch(function(){ $("err").textContent = "Could not reach the server."; $("go").disabled = false; });
});"""
    return shell("Log in - bloom-ledger", body, js)


def setup_page(needs_code=False, keep_settings=False):
    tz = "".join('<option value="%s">' % t for t in TZ_CHOICES)
    code_row = ('<div class="bl-field"><label for="code">Setup code</label><input id="code" autocomplete="off" required>'
                '<span class="bl-hint">Creating the account needs the one-time code the server printed in its log, on the line that says "Setup code". '
                'Docker: <code>docker compose logs bloom-ledger</code>. Mac install: <code>~/Library/Application Support/bloom-ledger-server/logs/server.log</code>. '
                'Or read the file <code>setup-code</code> in the data folder.</span></div>') if needs_code else ""
    money = ('<p class="bl-hint" style="margin-top:1.5rem">Your time zone and electricity price are already set from before. '
             'Setup leaves them as they are; change them in Accounting settings.</p>') if keep_settings else """<h2 style="margin-top:1.5rem">Where and what you pay</h2>
<div class="bl-field"><label for="tz">Time zone</label><input id="tz" list="tzs" autocomplete="off" required><datalist id="tzs">%(tz)s</datalist>
<span class="bl-hint">Days and months are cut at midnight in this zone.</span></div>
<div class="bl-field"><label for="rate">Electricity price per kWh (US dollars)</label><input id="rate" inputmode="decimal" placeholder="0.15">
<span class="bl-hint">Optional. Leave it empty and power cost stays "not computed" until you enter it in Accounting settings. Darkbloom pays in US dollars, so every figure here is in USD.</span></div>
"""
    body = """<main><div class="bl-narrow"><h1>Set up bloom-ledger</h1>
<p class="meta">Three short steps. Nothing leaves your network.</p>
<ol class="bl-steps" aria-label="Steps"><li id="s1" class="on">Your account</li><li id="s2">Electricity</li><li id="s3">Add a Mac</li></ol>

<form id="f1" class="bl-panel">
<h2>Create your login</h2>
<p class="bl-hint">This protects every change you make. One account is enough.</p>
%(code)s
<div class="bl-field"><label for="u">Username</label><input id="u" autocomplete="username" required autofocus></div>
<div class="bl-field"><label for="p">Password (8 or more characters)</label><input id="p" type="password" autocomplete="new-password" minlength="8" required></div>
<div class="bl-field"><label for="p2">Repeat the password</label><input id="p2" type="password" autocomplete="new-password" required></div>
%(money)s
<div class="bl-field"><label><input type="checkbox" id="gauge" style="min-height:auto"> I also use BloomGauge (optional)</label>
<span class="bl-hint">Not needed. bloom-ledger reads Darkbloom directly. This only records the choice.</span></div>
<p id="err1" class="bl-err" role="alert"></p>
<button class="primary" type="submit" id="go1">Create account and continue</button>
</form>

<section id="p2s" class="bl-panel" hidden>
<h2>Add your first Mac</h2>
<p class="bl-hint">Name the Mac (letters, numbers, dots, dashes), then run the command on that Mac in Terminal. The Mac needs Darkbloom installed.</p>
<form id="f2"><div class="bl-field"><label for="mid">Name</label><input id="mid" placeholder="mac-mini" pattern="[A-Za-z0-9][A-Za-z0-9._-]{0,63}" required></div>
<button class="primary" type="submit" id="go2">Get the install command</button> <span id="err2" class="bl-err" role="alert"></span></form>
<div id="cmdbox" hidden>
<p><strong>Paste this on the Mac:</strong></p>
<pre class="cmd" id="cmd"></pre>
<p id="selfonly" class="bl-err" hidden>This address only works on the machine running the ledger. For a different Mac, open this page using the ledger's network address (for example http://192.168.1.20:8787/setup) or its name, then get the command again.</p>
<button type="button" id="copy">Copy</button>
<p id="wait" class="bl-hint" role="status" aria-live="polite" style="margin-top:1rem">Waiting for first data from this Mac.</p>
<p class="bl-hint">The code works once and expires in 30 minutes. It usually takes one to three minutes after install for data to arrive.</p>
<p><button type="button" id="another">Add another Mac</button> <a class="btn primary" href="/status">Finish</a></p>
</div></section>
</div></main>""" % {"code": code_row, "tz": tz, "money": money % {"tz": tz} if not keep_settings else money}
    js = COMMON_JS + """
var mac = null, timer = null;
if ($("tz")) { try { $("tz").value = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; } catch (e) { $("tz").value = "UTC"; } }
function show2(){ $("f1").hidden = true; $("p2s").hidden = false; $("s1").className = "done"; $("s2").className = "done"; $("s3").className = "on"; }
api("GET", "/v1/auth/me").then(function(r){ if (r.body.mode === "login" && r.body.logged_in) show2(); else if (r.body.mode === "login") location.href = "/login?next=/setup"; });
$("f1").addEventListener("submit", function(e){
  e.preventDefault(); $("err1").textContent = "";
  if ($("p").value !== $("p2").value) { $("err1").textContent = "The two passwords do not match."; return; }
  $("go1").disabled = true;
  var body = {username: $("u").value, password: $("p").value, timezone: $("tz") ? $("tz").value : "", rate: $("rate") ? $("rate").value : "", bloomgauge: $("gauge").checked};
  if ($("code")) body.setup_code = $("code").value;
  api("POST", "/v1/auth/setup", body).then(function(r){
    if (r.status === 200) { show2(); } else { $("err1").textContent = r.body.error || "Setup failed."; $("go1").disabled = false; }
  }).catch(function(){ $("err1").textContent = "Could not reach the server."; $("go1").disabled = false; });
});
function poll(){
  api("GET", "/v1/status").then(function(r){
    var m = (r.body.machines || []).filter(function(x){ return x.id === mac; })[0];
    if (m && m.objects > 0) { $("wait").textContent = "Received data from " + mac + " (" + m.objects + " files). It is connected."; $("wait").className = "bl-ok"; clearInterval(timer); }
  });
}
$("f2").addEventListener("submit", function(e){
  e.preventDefault(); $("err2").textContent = ""; $("go2").disabled = true;
  api("POST", "/v1/settings/machines", {id: $("mid").value}).then(function(r){
    $("go2").disabled = false;
    if (r.status !== 201) { $("err2").textContent = r.body.error === "machine exists" ? "That name is taken. Pick another." : (r.body.error || "Could not add the Mac."); return; }
    return api("GET", "/v1/settings").then(function(s){
      var base = s.body.lan_url;
      if (!base) { $("err2").textContent = "The server does not know its own address. Open this page by its IP address or hostname, or set BLOOM_LEDGER_LAN_URL."; return; }
      mac = $("mid").value;
      $("cmd").textContent = "curl -fsSL " + base + "/install.sh | sh -s -- --pair " + r.body.pair_code;
      var h = (base.split("//")[1] || "").split(":")[0];
      $("selfonly").hidden = !(h === "localhost" || /^127[.]/.test(h));
      $("cmdbox").hidden = false; $("wait").textContent = "Waiting for first data from " + mac + "."; $("wait").className = "bl-hint";
      clearInterval(timer); timer = setInterval(poll, 3000);
    });
  });
});
$("copy").addEventListener("click", function(){ try { navigator.clipboard.writeText($("cmd").textContent); $("copy").textContent = "Copied"; } catch (e) { $("copy").textContent = "Select and copy by hand"; } });
$("another").addEventListener("click", function(){ $("cmdbox").hidden = true; $("mid").value = ""; clearInterval(timer); });"""
    return shell("Set up - bloom-ledger", body, js)


def status_page():
    body = """<main><h1>Status</h1>
<p id="overall" class="meta" role="status" aria-live="polite"><span class="bl-skel" style="display:inline-block;width:14rem">&nbsp;</span></p>
<section class="bl-panel"><h2>Macs</h2><div style="overflow-x:auto"><table id="macs" style="width:100%%;min-width:34rem">
<thead><tr><th scope="col">Mac</th><th scope="col">State</th><th scope="col">Last data</th><th scope="col">Files</th><th scope="col">What to do</th></tr></thead><tbody id="rows"></tbody></table></div>
<p id="none" class="note" hidden>No Macs yet. <a href="/setup">Add a Mac</a> or use Machines in the header.</p></section>
<section class="bl-panel"><h2>Alerts</h2><ul id="alerts" style="margin:0;padding-left:1.2rem"></ul><p id="noalerts" class="note" hidden>No open alerts.</p></section>
<section class="bl-panel"><h2>This server</h2><dl id="srv" style="display:grid;grid-template-columns:max-content 1fr;gap:.35rem 1.25rem;margin:0"></dl></section>
<section class="bl-panel"><h2>Optional integrations</h2><ul id="integ" style="margin:0;padding-left:1.2rem"></ul></section>
<p id="err" class="bl-err" role="alert"></p></main>"""
    js = COMMON_JS + """
function pill(cls, text){ var s = document.createElement("span"); s.className = "pill " + cls; s.textContent = text; return s; }
function td(child){ var c = document.createElement("td"); c.style.padding = ".5rem .6rem"; if (typeof child === "string") c.textContent = child; else c.appendChild(child); return c; }
var LABEL = {"reporting": ["ok", "Reporting"], "silent": ["bad", "Silent"], "not-reporting-yet": ["warn", "Waiting for data"], "removed": ["off", "Removed"]};
function bytes(n){ if (n == null) return "unknown"; var u = ["B","KB","MB","GB","TB"], i = 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return n.toFixed(i ? 1 : 0) + " " + u[i]; }
function render(s){
  $("err").textContent = "";
  $("overall").textContent = s.overall.text;
  var rows = $("rows"); rows.textContent = "";
  s.machines.forEach(function(m){
    var tr = document.createElement("tr"); var l = LABEL[m.status] || ["off", m.status];
    tr.appendChild(td(m.name === m.id ? m.id : m.name + " (" + m.id + ")")); tr.appendChild(td(pill(l[0], l[1])));
    tr.appendChild(td(m.age_text)); tr.appendChild(td(String(m.objects))); tr.appendChild(td(m.hint));
    rows.appendChild(tr);
  });
  $("none").hidden = s.machines.length > 0;
  var al = $("alerts"); al.textContent = "";
  s.alerts.forEach(function(a){ var li = document.createElement("li"); li.textContent = (a.alert === "machine-silent" ? "Silent: " : "Usage snapshot is stale: ") + a.machine_id + (a.age_s != null ? " (" + Math.round(a.age_s / 60) + " min)" : " (never received)"); al.appendChild(li); });
  $("noalerts").hidden = s.alerts.length > 0;
  var d = $("srv"); d.textContent = "";
  [["Version", s.version], ["Time zone", s.timezone], ["Login", {login: "on (admin account)", setup: "setup not finished", lan: "local network only (no admin yet)", off: "off (BLOOM_AUTH=off)"}[s.auth_mode] || s.auth_mode],
   ["Free disk space", bytes(s.disk_free_bytes)], ["Export API", s.export_api ? "on" : "off"]].forEach(function(kv){
    var a = document.createElement("dt"), b = document.createElement("dd"); a.textContent = kv[0]; a.className = "meta"; b.textContent = kv[1]; b.style.margin = "0"; d.appendChild(a); d.appendChild(b);
  });
  var ig = $("integ"); ig.textContent = "";
  s.integrations.forEach(function(i){ var li = document.createElement("li"); li.textContent = i.name + " (optional): " + (i.state === "enabled" ? "switched on" : "not set up") + ". " + i.detail; ig.appendChild(li); });
}
function load(){ api("GET", "/v1/status").then(function(r){ if (r.status === 200) render(r.body); else $("err").textContent = "Could not load status."; }).catch(function(){ $("err").textContent = "Could not reach the server."; }); }
load(); setInterval(load, 15000);"""
    return shell("Status - bloom-ledger", body.replace("%%", "%"), js)


def json_bytes(obj):
    return json.dumps(obj, sort_keys=True).encode()
