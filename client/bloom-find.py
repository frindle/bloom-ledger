#!/usr/bin/env python3
"""Find the ledger again when its LAN address changes (stdlib only; LaunchAgent, every 10 min).

Asks the configured ingest_url for GET /v1/hello. When that answers with this Mac's paired server_id, nothing
happens. Otherwise it scans this Mac's local /24 networks on the same port for a ledger that answers with the same
server_id and, when exactly one does, rewrites "ingest_url" in ~/.darkbloom/ledger.json (other keys kept).
Only private IPv4 addresses are tried, and nothing secret is sent: /v1/hello needs no token.
Env: BLOOM_POWER_HOME (default ~/.darkbloom)."""
import argparse
import concurrent.futures as cf
import ipaddress
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_PORT = 8787
HELLO_TIMEOUT_S = 3.0
SCAN_TIMEOUT_S = 0.8
WORKERS = 64


def home_dir():
    return Path(os.environ.get("BLOOM_POWER_HOME") or Path.home() / ".darkbloom")


def read_config(home):
    try:
        cfg = json.loads((Path(home) / "ledger.json").read_text())
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def write_url(home, url):
    """Set ingest_url in ledger.json atomically, keeping every other key."""
    p = Path(home) / "ledger.json"
    cfg = read_config(home)
    cfg["ingest_url"] = url
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, p)


def hello(base, timeout, opener=urllib.request.urlopen):
    """The server_id a ledger at `base` reports, or None."""
    try:
        with opener(base.rstrip("/") + "/v1/hello", timeout=timeout) as r:
            data = json.loads(r.read(4096))
    except Exception:  # noqa: BLE001 - any failure just means "not this host"
        return None
    if isinstance(data, dict) and data.get("service") == "bloom-ledger" and isinstance(data.get("server_id"), str):
        return data["server_id"]
    return None


def local_networks(ifconfig_text=None):
    """Private IPv4 /24 networks this Mac has an address on (from ifconfig; loopback and link-local skipped)."""
    if ifconfig_text is None:
        try:
            ifconfig_text = subprocess.run(["/sbin/ifconfig"], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            ifconfig_text = ""
    nets = []
    for m in re.finditer(r"\binet (\d+\.\d+\.\d+\.\d+)", ifconfig_text):
        ip = ipaddress.ip_address(m.group(1))
        if ip.is_private and not ip.is_loopback and not ip.is_link_local:
            net = ipaddress.ip_network(m.group(1) + "/24", strict=False)
            if net not in nets:
                nets.append(net)
    return nets


def scan(server_id, port, nets, probe=None):
    """Base URLs on `nets` whose /v1/hello answers with `server_id`."""
    probe = probe or (lambda base: hello(base, SCAN_TIMEOUT_S))
    bases = ["http://%s:%d" % (h, port) for n in nets for h in n.hosts()]
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        return sorted(b for b, sid in zip(bases, ex.map(probe, bases)) if sid == server_id)


def run(home, probe=None, nets=None):
    """One pass. Returns a short status word (also printed)."""
    cfg = read_config(home)
    sid, url = cfg.get("server_id"), str(cfg.get("ingest_url") or "")
    if not isinstance(sid, str) or not re.fullmatch(r"[0-9a-f]{32}", sid):
        return "not-paired"
    probe = probe or (lambda base: hello(base, HELLO_TIMEOUT_S))
    if url and probe(url) == sid:
        return "ok"
    port = (urlparse(url).port or DEFAULT_PORT) if url else DEFAULT_PORT
    found = scan(sid, port, local_networks() if nets is None else nets, probe)
    if len(found) != 1:
        return "not-found" if not found else "ambiguous"
    write_url(home, found[0])
    return "moved"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.parse_args(argv)
    status = run(home_dir())
    if status != "ok":
        print("bloom-find: " + status + (" " + read_config(home_dir()).get("ingest_url", "") if status == "moved" else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
