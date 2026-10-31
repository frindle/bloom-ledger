"""Test support (frozen): render the home page from bloom_accounting_page and run its inline script in dom_harness.js."""
import json
import subprocess
from pathlib import Path

import bloom_accounting_page as PG

HERE = Path(__file__).resolve().parent


def run_home(tmp_path, fetch, steps=None):
    page = tmp_path / "home.html"
    page.write_text(PG.render_page())
    sp = tmp_path / "scenario.json"
    sp.write_text(json.dumps({"fetch": fetch, "steps": steps or []}))
    res = subprocess.run(["node", str(HERE / "dom_harness.js"), str(page), str(sp)], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0 and res.stdout, f"harness failed: {res.stderr[-600:]}"
    return json.loads(res.stdout)
