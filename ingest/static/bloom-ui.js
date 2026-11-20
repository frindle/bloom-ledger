/* bloom-ledger page chrome: header with every page, theme toggle, login state, finish-setup notice. No dependencies. */
(function () {
  var LINKS = [["/", "Home"], ["/status", "Status"], ["/log", "Day log"], ["/tax", "Tax"], ["/settings", "Machines"],
               ["/settings/accounting", "Accounting"], ["/settings/depreciation", "Depreciation"]];
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
  var theme = store("bl-theme");
  if (theme === "light" || theme === "dark") document.documentElement.setAttribute("data-theme", theme);
  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    for (var k in (attrs || {})) e.setAttribute(k, attrs[k]);
    if (text) e.textContent = text;
    return e;
  }
  function build() {
    if (document.querySelector(".bl-nav") || document.body.hasAttribute("data-bare")) return;
    var nav = el("header", {"class": "bl-nav", role: "banner"});
    var inner = el("nav", {"class": "bl-nav-in", "aria-label": "Main"});
    inner.appendChild(el("a", {"class": "bl-brand", href: "/"}, "bloom-ledger"));
    var here = location.pathname.replace(/\/$/, "") || "/";
    LINKS.forEach(function (l) {
      var a = el("a", {"class": "bl-link", href: l[0]}, l[1]);
      if (l[0] === here) a.setAttribute("aria-current", "page");
      inner.appendChild(a);
    });
    inner.appendChild(el("span", {"class": "bl-spacer"}));
    var auth = el("span", {id: "bl-auth"});
    inner.appendChild(auth);
    var tb = el("button", {type: "button", "aria-label": "Switch colour theme", title: "Switch colour theme"}, "Theme");
    tb.addEventListener("click", function () {
      var cur = document.documentElement.getAttribute("data-theme");
      var dark = cur ? cur === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      var next = dark ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      store("bl-theme", next);
    });
    inner.appendChild(tb);
    nav.appendChild(inner);
    document.body.insertBefore(nav, document.body.firstChild);
    fetch("/v1/auth/me", {credentials: "same-origin"}).then(function (r) { return r.json(); }).then(function (me) {
      if (me.mode === "setup" && here === "/") { location.replace("/setup"); return; }
      if (me.mode === "setup" && here !== "/setup") {
        var n = el("div", {"class": "bl-notice", role: "status"});
        n.appendChild(document.createTextNode("Setup is not finished. "));
        n.appendChild(el("a", {href: "/setup"}, "Finish setup"));
        nav.parentNode.insertBefore(n, nav.nextSibling);
      }
      if (me.mode === "login") {
        if (me.logged_in) {
          var b = el("button", {type: "button"}, "Log out");
          b.addEventListener("click", function () { fetch("/v1/auth/logout", {method: "POST", credentials: "same-origin"}).then(function () { location.href = "/login"; }); });
          auth.appendChild(b);
        } else if (here !== "/login") {
          auth.appendChild(el("a", {"class": "bl-link", href: "/login"}, "Log in"));
        }
      }
    }).catch(function () {});
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build); else build();
})();
