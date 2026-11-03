#!/usr/bin/env python3
"""Archive Darkbloom's rolling local records into the ledger spool before they roll off (stdlib only).

  bloom-archive.py            one pass (launchd every 15 min): usage-history ring entries not seen yet, new lines
                              of provider.log / power CSVs / earnings jsonl, changed lifecycle files, and an
                              archive-run heartbeat -> ~/.darkbloom/ledger-spool/<kind>/<sha256>.obj

Env: BLOOM_POWER_HOME (default ~/.darkbloom), BLOOM_MACHINE_ID (else ledger.json, else m4max). Reads no secrets;
never touches auth_token, provider.toml or the darkbloom CLI. Exit 0 also when another run holds the lock.
See the bloom-ledger README."""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bloom_archive as A  # noqa: E402
import bloom_ledger as LG  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spool", help="spool dir (default <home>/ledger-spool)")
    a = ap.parse_args(argv)
    home = LG.home_dir()
    spool = Path(a.spool) if a.spool else home / A.SPOOL_DIRNAME
    lock, state = A.lock_and_load_state(spool)
    if lock is None:
        print("bloom-archive: another run holds the lock", file=sys.stderr)
        return 0
    now = time.time()
    counts, err = {}, ""
    try:
        counts = A.archive_once(home, spool, state, now, LG.resolve_machine_id(home))
    except Exception as e:  # noqa: BLE001 - state already reflects every object written; record and keep going
        err = f"{type(e).__name__}: {e}"
    finally:
        A.save_state(spool, state)
        A.log_run(spool, now, counts, err)
        lock.close()
    print(A.canonical({"counts": counts, "error": err}))
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())
