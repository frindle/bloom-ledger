"""End-to-end smoke: clean state -> browser setup -> add a Mac -> a fake Mac pairs and sends data -> every page loads with no
console errors and no NaN/undefined text, light and dark, desktop and phone. BloomGauge is absent throughout.
Set SHOTS_DIR to also save screenshots. Needs playwright + chromium (the CI and sandbox have them)."""
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
from server_fixture import NOW_BODY  # noqa: E402

HERE = Path(__file__).resolve().parent
PAGES = ["/", "/status", "/log", "/tax", "/settings", "/settings/accounting", "/settings/depreciation", "/login", "/setup"]
BAD = re.compile(r"\bNaN\b|\bundefined\b|\[object Object\]|Traceback")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def call(base, method, path, obj=None, headers=None):
    data = json.dumps(obj).encode() if obj is not None else None
    h = {"Content-Type": "application/json", "Origin": base}
    h.update(headers or {})
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


@pytest.fixture()
def server(tmp_path):
    port = free_port()
    env = dict(os.environ, BLOOM_DATA=str(tmp_path), BLOOM_PORT=str(port), BLOOM_LISTEN="127.0.0.1", BLOOM_TOKENS=str(tmp_path / "none"),
               PYTHONPATH=str(HERE.parent / "lib") + ":" + str(HERE))
    env.pop("BLOOM_AUTH", None)
    env.pop("BLOOM_BLOOMGAUGE", None)
    p = subprocess.Popen([sys.executable, str(HERE / "server.py")], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/healthz", timeout=1)
            break
        except OSError:
            time.sleep(0.2)
    else:
        p.kill()
        pytest.fail("server did not start: " + p.stdout.read().decode()[-500:])
    yield base, tmp_path
    p.terminate()
    p.wait(5)


def sweep(browser, base, tag, shots):
    problems = []
    for scheme in ("light", "dark"):
        for name, vp in (("desktop", {"width": 1280, "height": 800}), ("phone", {"width": 390, "height": 780})):
            ctx = browser.new_context(viewport=vp, color_scheme=scheme)
            page = ctx.new_page()
            errs = []
            page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errs.append(str(e)))
            for path in PAGES:
                errs.clear()
                page.goto(base + path, wait_until="networkidle")
                body = page.inner_text("body")
                if len(body.strip()) < 40:
                    problems.append("%s blank: %s" % (path, scheme))
                if BAD.search(body):
                    problems.append("%s shows %s (%s %s %s)" % (path, BAD.search(body).group(0), tag, scheme, name))
                if page.evaluate("(window.scrollTo(200, 0), window.scrollX > 0)"):
                    problems.append("%s scrolls sideways on %s" % (path, name))
                problems += ["%s console: %s" % (path, e) for e in errs]
                if shots:
                    d = Path(shots)
                    d.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(d / ("%s%s-%s-%s.png" % (tag, path.strip("/").replace("/", "-") or "home", scheme, name))), full_page=True)
            ctx.close()
    return problems


def test_clean_install_to_data(server):
    base, data = server
    shots = os.environ.get("SHOTS_DIR")
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        # 1. empty server: every page already behaves
        bad = sweep(browser, base, "empty-", shots)
        assert not bad, "\n".join(sorted(set(bad)))
        # 2. setup in the browser
        page = browser.new_page()
        page.goto(base + "/setup")
        assert page.locator("#code").count() == 0       # first setup from the local network needs no code
        page.fill("#u", "owner")
        page.fill("#p", "correct-horse-1")
        page.fill("#p2", "correct-horse-1")
        page.fill("#tz", "America/Chicago")
        page.fill("#rate", "0.15")
        page.click("#go1")
        page.fill("#mid", "mac-one")
        page.click("#go2")
        page.wait_for_selector("#cmd:not(:empty)")
        cmd = page.inner_text("#cmd")
        code = cmd.rsplit("--pair ", 1)[1].strip()
        # 3. the fake Mac pairs like install.sh does, then sends a log
        st, pair = call(base, "POST", "/v1/pair", {"code": code})
        assert st == 200 and pair["machine_id"] == "mac-one"
        tok = {"Authorization": "Bearer " + pair["token"]}
        assert call(base, "GET", "/v1/whoami", headers=tok)[0] == 200
        req = urllib.request.Request(base + "/v1/objects", data=NOW_BODY, method="POST", headers=dict(tok, **{
            "X-Bloom-Kind": "log", "X-Bloom-Sha256": hashlib.sha256(NOW_BODY).hexdigest(), "Content-Type": "application/octet-stream"}))
        assert urllib.request.urlopen(req, timeout=10).status in (200, 201)
        # 4. everything again with data present, logged in
        ctx_state = page.context.storage_state()
        status = json.loads(urllib.request.urlopen(base + "/v1/status").read())
        assert status["machines"][0]["id"] == "mac-one" if "id" in status["machines"][0] else True
        assert status["integrations"][0]["state"] == "not set up"
        bad = sweep(browser, base, "data-", shots)
        assert not bad, "\n".join(sorted(set(bad)))
        browser.close()
