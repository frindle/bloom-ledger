"""Frozen test: bloom_accounting_settings_form.settings_form_script, run in node without a DOM. Fake values only."""
import json
import shutil
import subprocess

import pytest

import bloom_accounting_settings_form as F

HARNESS = """
const calls = [];
global.fetch = (u, o) => { calls.push({u, o}); return Promise.resolve({ok: calls.length < %d, status: 500}); };
%s
const ITEMS = [{key: "dep_life_months", type: "int", raw: " 60 "}, {key: "m5_lease_start", type: "text", raw: ""},
  {key: "rate_schedule", type: "json", raw: '[{"months": [1]}]'}, {key: "dep_method", type: "text", raw: "macrs5"}];
const out = {updates: buildUpdates(ITEMS, "2026-10-01")};
for (const bad of [{key: "x_int", type: "int", raw: "1.5"}, {key: "x_json", type: "json", raw: "{oops"}]) {
  try { buildUpdates([bad], "2026-10-01"); out[bad.key] = "no error"; } catch (e) { out[bad.key] = e.message; }
}
sendUpdates(out.updates).then((k) => { out.sent = k; return sendUpdates(out.updates); }).catch((e) => { out.fail = e.message; }).then(() => {
  out.calls = calls.map((c) => [c.u, c.o.method, c.o.headers["Content-Type"], JSON.parse(c.o.body).key]);
  console.log(JSON.stringify(out));
});
"""


def run(ok_calls):
    out = subprocess.run(["node", "-e", HARNESS % (ok_calls, F.settings_form_script())], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_build_updates_skips_blank_and_converts_types():
    r = run(99)
    assert r["updates"] == [{"key": "dep_life_months", "value": 60, "effective_from": "2026-10-01"},
                            {"key": "rate_schedule", "value": [{"months": [1]}], "effective_from": "2026-10-01"},
                            {"key": "dep_method", "value": "macrs5", "effective_from": "2026-10-01"}]
    assert r["x_int"].startswith("x_int:") and r["x_json"].startswith("x_json:")


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_send_updates_posts_in_order_and_stops_at_first_failure():
    r = run(99)
    assert r["sent"] == ["dep_life_months", "rate_schedule", "dep_method"]
    assert r["calls"][0] == ["/v1/accounting/settings", "POST", "application/json", "dep_life_months"]
    r = run(2)
    assert r["fail"] == "rate_schedule: HTTP 500" and "sent" not in r
    assert [c[3] for c in r["calls"]] == ["dep_life_months", "rate_schedule"]


def test_script_is_plain_text_without_dom_injection():
    src = F.settings_form_script()
    assert "<script" not in src and "innerHTML" not in src and "eval(" not in src and "=>" not in src
    assert "/v1/accounting/settings" in src
