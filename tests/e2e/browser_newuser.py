#!/usr/bin/env python3
"""Browser walk of the new-user path against a running server (the Docker compose stack in CI). Fake data only.
  browser_newuser.py BASE SHOTS_DIR
First visit -> /setup -> create admin -> get the install command -> log out -> wrong password -> lockout -> log in again ->
every page with empty data -> a fake Mac pairs and ships sample data -> every page again, light and dark, desktop and phone,
with no console errors, no NaN/undefined text and no sideways scrolling. Screenshots go to SHOTS_DIR."""
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
BASE = sys.argv[1].rstrip("/")
SHOTS = Path(sys.argv[2])
SHOTS.mkdir(parents=True, exist_ok=True)
PAGES = ["/", "/status", "/log", "/tax", "/settings", "/settings/accounting", "/settings/depreciation", "/login", "/setup"]
BAD = re.compile(r"\bNaN\b|\bundefined\b|\[object Object\]|Traceback|Internal Server Error")
PW = "correct-horse-1"
fails = []


def check(cond, msg):
    print(("ok   - " if cond else "FAIL - ") + msg, flush=True)
    if not cond:
        fails.append(msg)


def shot(page, name):
    page.screenshot(path=str(SHOTS / (name + ".png")), full_page=True)


def sweep(browser, state, tag):
    for scheme in ("light", "dark"):
        for name, vp in (("desktop", {"width": 1280, "height": 800}), ("phone", {"width": 390, "height": 780})):
            ctx = browser.new_context(viewport=vp, color_scheme=scheme, storage_state=state)
            page = ctx.new_page()
            errs = []
            page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errs.append(str(e)))
            for path in PAGES:
                errs.clear()
                page.goto(BASE + path, wait_until="networkidle")
                label = "%s %s %s %s" % (tag, path, scheme, name)
                body = page.inner_text("body")
                check(len(body.strip()) >= 40, label + ": not blank")
                m = BAD.search(body)
                check(not m, label + ": no NaN/undefined text" + (" (found %s)" % m.group(0) if m else ""))
                over = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                check(over <= 1, label + ": no sideways scroll (%spx over)" % over)
                check(not errs, label + ": no console errors" + (" %s" % errs[:2] if errs else ""))
                shot(page, "%s-%s-%s-%s" % (tag, path.strip("/").replace("/", "-") or "home", scheme, name))
            ctx.close()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()

        # 1. first visit lands on setup
        page.goto(BASE + "/", wait_until="networkidle")
        check(page.url.rstrip("/").endswith("/setup"), "first visit to / lands on /setup (at %s)" % page.url)
        shot(page, "01-first-visit")
        # login page on a fresh server sends you to setup too
        page.goto(BASE + "/login", wait_until="networkidle")
        check(page.url.rstrip("/").endswith("/setup"), "/login on a fresh server goes to /setup")

        # 2. setup: bad input says what is wrong, then success
        page.fill("#u", "owner")
        page.fill("#p", PW)
        page.fill("#p2", "something-else-1")
        page.click("#go1")
        check("do not match" in page.inner_text("#err1"), "mismatched passwords say so")
        page.fill("#p", "short")
        page.fill("#p2", "short")
        page.evaluate("document.getElementById('p').removeAttribute('minlength')")
        page.click("#go1")
        page.wait_for_function("document.getElementById('err1').textContent.length > 0")
        check("8" in page.inner_text("#err1"), "short password says how long it must be: %r" % page.inner_text("#err1"))
        page.fill("#p", PW)
        page.fill("#p2", PW)
        page.fill("#tz", "Not/AZone")
        page.click("#go1")
        page.wait_for_function("document.getElementById('err1').textContent.length > 0")
        check("time zone" in page.inner_text("#err1").lower(), "bad time zone says so: %r" % page.inner_text("#err1"))
        page.fill("#tz", "America/Chicago")
        page.fill("#rate", "abc")
        page.click("#go1")
        page.wait_for_function("document.getElementById('err1').textContent.length > 0")
        check("number" in page.inner_text("#err1").lower(), "bad price says so: %r" % page.inner_text("#err1"))
        page.fill("#rate", "0.15")
        page.click("#go1")
        page.wait_for_selector("#p2s:not([hidden])")
        shot(page, "02-setup-step2")
        page.fill("#mid", "mac-one")
        page.click("#go2")
        page.wait_for_selector("#cmd:not(:empty)")
        cmd = page.inner_text("#cmd")
        check("--pair " in cmd and "/install.sh" in cmd, "setup shows an install command: %s" % re.sub(r"--pair \S+", "--pair <code>", cmd))
        shot(page, "03-setup-command")
        code = cmd.rsplit("--pair ", 1)[1].strip()
        page.fill("#mid", "mac-one")
        page.click("#go2")
        page.wait_for_function("document.getElementById('err2').textContent.length > 0")
        check("taken" in page.inner_text("#err2"), "re-using a Mac name says it is taken")

        # 3. log out, wrong password, lockout, right password
        page.goto(BASE + "/status", wait_until="networkidle")
        page.click("text=Log out")
        page.wait_for_url("**/login")
        page.fill("#u", "owner")
        page.fill("#p", "wrong-password")
        page.click("#go")
        page.wait_for_function("document.getElementById('err').textContent.length > 0")
        msg = page.inner_text("#err")
        check("wrong" in msg.lower() and "password" in msg.lower(), "wrong password message is clear: %r" % msg)
        shot(page, "04-wrong-password")
        for _ in range(5):
            page.fill("#p", "wrong-password")
            page.click("#go")
            page.wait_for_timeout(400)
        msg = page.inner_text("#err")
        check("wait" in msg.lower() and "minute" in msg.lower(), "lockout message says to wait a minute: %r" % msg)
        shot(page, "05-locked-out")
        page.fill("#p", PW)
        page.click("#go")
        page.wait_for_timeout(700)
        check(page.url.endswith("/login") or "/login" in page.url, "the right password is also refused while locked")
        print("waiting for the lock to expire ...", flush=True)
        time.sleep(65)
        page.fill("#p", PW)
        page.click("#go")
        page.wait_for_url(lambda u: "/login" not in u, timeout=10000)
        check(True, "logging in works once the lock has expired")
        state = ctx.storage_state()
        # a password manager style visit to /setup after setup is done
        page.goto(BASE + "/setup", wait_until="networkidle")
        check(page.locator("#p2s").is_visible(), "/setup after setup, logged in, goes straight to adding a Mac")

        # 4. empty data
        sweep(browser, state, "empty")

        # 5. a fake Mac pairs like install.sh does and ships sample data
        req = urllib.request.Request(BASE + "/v1/pair", data=json.dumps({"code": code}).encode(), method="POST", headers={"Content-Type": "application/json"})
        pair = json.loads(urllib.request.urlopen(req, timeout=10).read())
        subprocess.run([sys.executable, str(HERE / "sample.py"), "post", BASE, pair["token"]], check=True)
        page.goto(BASE + "/setup", wait_until="networkidle")
        page.fill("#mid", "mac-two")
        page.click("#go2")
        page.wait_for_selector("#cmd:not(:empty)")
        page.goto(BASE + "/status", wait_until="networkidle")
        txt = page.inner_text("body")
        check("mac-one" in txt and "Reporting" in txt, "status shows the Mac as reporting after data arrives")
        shot(page, "06-status-with-data")
        page.goto(BASE + "/", wait_until="networkidle")
        check("$" in page.inner_text("body"), "home shows dollar figures once data arrived")

        # 6. everything again with sample data
        sweep(browser, state, "data")
        browser.close()
    print("\n%d failures" % len(fails))
    for f in fails:
        print("  -", f)
    sys.exit(1 if fails else 0)


main()
