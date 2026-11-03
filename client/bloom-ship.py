#!/usr/bin/env python3
"""Push the Darkbloom ledger spool to the Unraid bloom-ledger ingest (stdlib only; launchd every 60 s).

  bloom-ship.py              one pass: POST pending ~/.darkbloom/ledger-spool/<kind>/*.obj, oldest first
  bloom-ship.py --check      print the ingest URL, whether a token was found (never the token), pending count

Config: BLOOM_INGEST_URL, else "ingest_url" in ~/.darkbloom/ledger.json (must be a literal LAN IP URL, e.g.
http://10.0.7.143:8787). Token: BLOOM_SHIP_TOKEN, else the login Keychain item service "bloom-ledger-ingest",
account <machine_id>. Machine id as in bloom-manifest.py. See the bloom-ledger README."""
import argparse
import fcntl
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bloom_archive as A  # noqa: E402
import bloom_ledger as LG  # noqa: E402
import bloom_power_lib as P  # noqa: E402
import bloom_ship as S  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spool", help="spool dir (default <home>/ledger-spool)")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    home = LG.home_dir()
    spool = Path(a.spool) if a.spool else home / A.SPOOL_DIRNAME
    mid = LG.resolve_machine_id(home)
    url = S.ingest_url(home)
    token = (os.environ.get("BLOOM_SHIP_TOKEN") or "").strip() or S.keychain_token(mid)
    if a.check:
        print(A.canonical({"machine_id": mid, "url": url, "lan_ok": S.is_lan_url(url), "token_found": bool(token),
                           "pending": len(S.pending(spool)) if spool.is_dir() else 0}))
        return 0
    if not S.is_lan_url(url):
        print("bloom-ship: no LAN ingest URL configured (BLOOM_INGEST_URL / ledger.json ingest_url)", file=sys.stderr)
        return 2
    if not token:
        print(f"bloom-ship: no ingest token in Keychain for account {mid}", file=sys.stderr)
        return 2
    spool.mkdir(parents=True, exist_ok=True)
    with open(spool / ".ship.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return 0
        state = S.load_state(spool)
        now = time.time()
        res = S.ship_run(spool, url, token, state, now)
        S.save_state(spool, state)
    if res["ok"] or res["rejected"] or res["stopped"] not in ("", "backoff"):
        rec = {"at": P.utc_iso(now), **res, "fails": state.get("fails", 0)}
        P.append_line(spool / "ship.log", A.canonical(rec))
    return 1 if res["stopped"] == "auth" else 0


if __name__ == "__main__":
    sys.exit(main())
