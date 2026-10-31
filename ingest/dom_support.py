"""Test support (frozen): run an HTML page's inline script against dom_harness.js and query the serialized DOM."""
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_page(tmp_path, fetch, steps=None, page="settings.html", origin=None):
    scenario = {"fetch": fetch, "steps": steps or []}
    if origin:
        scenario["origin"] = origin
    sp = tmp_path / "scenario.json"
    sp.write_text(json.dumps(scenario))
    res = subprocess.run(["node", str(HERE / "dom_harness.js"), str(HERE / page), str(sp)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0 and res.stdout, f"harness failed: {res.stderr[-600:]}"
    return json.loads(res.stdout)


def find(node, id_):
    if node["id"] == id_:
        return node
    for c in node["children"]:
        hit = find(c, id_)
        if hit:
            return hit
    return None


def walk(node):
    yield node
    for c in node["children"]:
        yield from walk(c)


def rows(result, tbody_id="machine-rows"):
    """[[cell text, ...], ...] for every <tr> under the tbody."""
    body = find(result["dom"], tbody_id)
    return [[c["text"].strip() for c in tr["children"] if c["tag"] in ("td", "th")]
            for tr in body["children"] if tr["tag"] == "tr"]


def texts(node, tag):
    return [n["text"].strip() for n in walk(node) if n["tag"] == tag]
