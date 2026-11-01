"""Frozen test: bloom_accounting_settings_form.settings_form_wiring, run in node against a fake DOM with stubbed helpers."""
import json
import shutil
import subprocess

import pytest

import bloom_accounting_settings_form as F

HARNESS = """
const els = {}; const log = {};
function el(id) { return els[id] || (els[id] = {id, value: "2026-10-01", textContent: "", listeners: {}, addEventListener(n, f) { this.listeners[n] = f; }}); }
const fields = [{a: {"data-key": "dep_life_months", "data-type": "int"}, value: "60"}, {a: {"data-key": "dep_method"}, value: "macrs5"}]
  .map((f) => ({value: f.value, getAttribute: (k) => f.a[k] === undefined ? null : f.a[k]}));
global.document = {getElementById: el, querySelectorAll: (sel) => { log.sel = sel; return fields; }};
global.buildUpdates = (items, eff) => { log.items = items; log.eff = eff; if (%s) { throw new Error("boom"); } return ["u"]; };
global.sendUpdates = (u) => Promise.resolve(%s);
%s
let prevented = false;
el("acct-form").listeners.submit({preventDefault() { prevented = true; }});
setTimeout(() => console.log(JSON.stringify({log, prevented, status: el("status").textContent, events: Object.keys(el("acct-form").listeners)})), 20);
"""


def run(throws, keys):
    out = subprocess.run(["node", "-e", HARNESS % (throws, keys, F.settings_form_wiring())], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_submit_collects_fields_and_reports_saved_keys():
    r = run("false", '["a", "b"]')
    assert r["events"] == ["submit"] and r["prevented"] is True and r["log"]["sel"] == "[data-key]" and r["log"]["eff"] == "2026-10-01"
    assert r["log"]["items"] == [{"key": "dep_life_months", "type": "int", "raw": "60"}, {"key": "dep_method", "type": "text", "raw": "macrs5"}]
    assert r["status"] == "Saved: a, b"
    assert run("false", "[]")["status"] == "Saved: nothing to save"


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_validation_error_is_shown_not_thrown():
    assert run("true", "[]")["status"] == "Failed: boom"


def test_wiring_is_plain_text_without_dom_injection():
    src = F.settings_form_wiring()
    assert "<script" not in src and "innerHTML" not in src and "eval(" not in src and "=>" not in src and "acct-form" in src
