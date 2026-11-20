#!/usr/bin/env python3
"""bloom-doctor: check this Mac's bloom-ledger client end to end and say how to fix anything wrong.
Read-only: it never writes to Darkbloom's folder, never prints the token. Exit 1 on any FAIL.
  python3 bloom-doctor.py [--home ~/.darkbloom]"""
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bloom_ship as S  # noqa: E402

JOBS = ("power", "archive", "ship", "manifest", "find")


def get(url, token=None, timeout=6):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with S.open_no_redirect(req, timeout=timeout) as r:  # never follow a redirect with the token attached
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, OSError, ValueError):
        return None, b""


def checks(home, env=None, fetch=get, keychain=S.keychain_token, loaded=None, which=shutil.which):
    """[(status, name, detail, fix)]; status PASS, WARN, FAIL or INFO. Never raises."""
    home = Path(home)
    out = []

    def add(s, n, d="", f=""):
        out.append((s, n, d, f))

    try:
        cfg = json.loads((home / "ledger.json").read_text())
        cfg = cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        cfg = {}
    mid, url = cfg.get("machine_id"), S.ingest_url(home, env)
    if not mid or not url:
        add("FAIL", "This Mac is paired", "no %s" % (home / "ledger.json"),
            "Run the install command from the ledger's Setup page (curl ... | sh -s -- --pair CODE).")
        return out
    add("PASS", "This Mac is paired", "machine %s" % mid)
    add("PASS" if S.is_lan_url(url) else "FAIL", "Ledger address looks right", url,
        "Use your server's local address or name, e.g. http://192.168.1.20:8787. Rerun the installer with --server.")
    st, _ = fetch(url.rstrip("/") + "/v1/hello")
    if st == 200:
        add("PASS", "Ledger is reachable", url)
    else:
        add("FAIL", "Ledger is reachable", "no answer from %s" % url,
            "Check the server is running, this Mac is on the same network or VPN, and the address is right.")
    token = keychain(mid)
    if token:
        add("PASS", "Token is in the Keychain")
        st, _ = fetch(url.rstrip("/") + "/v1/whoami", token)
        if st == 200:
            add("PASS", "Ledger accepts this Mac's token")
        elif st in (401, 403):
            add("FAIL", "Ledger accepts this Mac's token", "refused",
                "The token was revoked or the server was reset. Make a new pairing code on the Setup page and rerun the installer.")
        else:
            add("WARN", "Ledger accepts this Mac's token", "could not check", "Fix the connection first.")
    else:
        add("FAIL", "Token is in the Keychain", "missing",
            "Make a new pairing code on the Setup page and rerun the installer. Allow Keychain access if macOS asks.")
    dark = [p for p in home.glob("*") if p.name not in ("ledger.json",)] if home.is_dir() else []
    add("PASS" if dark else "WARN", "Darkbloom data present (read only)", "%d items in %s" % (len(dark), home) if dark else "none yet",
        "Run Darkbloom on this Mac for a while. The ledger only reads what Darkbloom writes and never changes it.")
    add("PASS" if which("macmon") or Path("/opt/homebrew/bin/macmon").exists() or Path("/usr/local/bin/macmon").exists() else "WARN",
        "macmon (power sensor)", "", "brew install macmon. Without it earnings still work but power shows as unavailable.")
    if loaded is None:
        loaded = lambda label: subprocess.run(["launchctl", "print", "gui/%d/%s" % (os.getuid(), label)], capture_output=True).returncode == 0
    missing = [j for j in JOBS if not loaded("dev.bloom-ledger." + j)]
    add("FAIL" if missing else "PASS", "Background jobs loaded", ("not loaded: " + ", ".join(missing)) if missing else "%d of %d" % (len(JOBS), len(JOBS)),
        "Rerun the installer; it is safe to run again.")
    add("INFO", "BloomGauge (optional)", "switched on" if cfg.get("bloomgauge") else "optional: not set up", "Nothing to do. It is never required.")
    return out


def main(argv):
    home = Path(os.path.expanduser("~/.darkbloom"))
    if len(argv) > 2 and argv[1] == "--home":
        home = Path(argv[2])
    rows = checks(home)
    for s, n, d, f in rows:
        print("[%-4s] %s%s" % (s, n, (": " + d) if d else ""))
        if s in ("FAIL", "WARN") and f:
            print("       fix: " + f)
    bad = sum(1 for r in rows if r[0] == "FAIL")
    print("\n" + ("All required checks passed." if not bad else "%d check%s failed." % (bad, "" if bad == 1 else "s")))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
