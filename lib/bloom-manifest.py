#!/usr/bin/env python3
"""Daily hash-chained manifest of the Darkbloom bookkeeping data (stdlib only).

  bloom-manifest.py [daily] [--day YYYY-MM-DD]   close UTC day(s) up to --day (default: yesterday UTC): write
                                                 ~/.darkbloom/ledger/manifest-<day>.json (append-only; missed days
                                                 are backfilled; a re-run of a written day is a no-op)
  bloom-manifest.py verify                       walk the chain, re-hash every file range; rc 1 on any problem

Env: BLOOM_POWER_HOME (default ~/.darkbloom), BLOOM_MACHINE_ID (else "machine_id" in ~/.darkbloom/ledger.json,
else m4max). Reads no secrets.
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bloom_ledger as L  # noqa: E402


def collect_files(home, day):
    """Closed range of every raw file under `home` for UTC day `day`: [{'path': path relative to home (posix),
    'bytes', 'sha256'}] sorted by path. Files with no closed bytes are left out."""
    cutoff = L.day_cutoff(day)
    result = []
    for pattern in L.RAW_GLOBS:
        for p in Path(home).glob(pattern):
            n = L.closed_length(p, cutoff)
            if n == 0:
                continue
            result.append({"path": p.relative_to(home).as_posix(), "bytes": n, "sha256": L.file_digest(p, n)})
    return sorted(result, key=lambda f: f["path"])


def daily_run(home, day, machine_id):
    """Write the manifests for every day after the newest existing one up to `day` (only `day` when the ledger is
    empty or already reaches `day`), each chained to the newest manifest before it.
    Returns (rc, [(date, 'written'|'same'|'conflict')]): rc 1 at the first conflict (stops there), else 0."""
    ledger = Path(home) / L.LEDGER_DIRNAME
    have = {}
    for date, manifest in L.load_manifests(ledger):
        if manifest is not None:
            have[date] = manifest
    if have:
        newest = max(have.keys())
        if newest < day:
            days_to_write = L.days_after(newest, day)
        else:
            days_to_write = [day]
    else:
        days_to_write = [day]
    rc = 0
    res = []
    for d in days_to_write:
        prev = None
        for existing_date in sorted(have.keys()):
            if existing_date < d:
                prev = have[existing_date]
        m = L.make_manifest(d, machine_id, collect_files(home, d), prev)
        st = L.write_manifest(ledger, m)
        res.append((d, st))
        if st == "conflict":
            rc = 1
            break
        elif st == "written":
            have[d] = m
    return rc, res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", nargs="?", default="daily", choices=("daily", "verify"))
    ap.add_argument("--day", help="UTC day to close, YYYY-MM-DD (default: yesterday UTC)")
    a = ap.parse_args(argv)
    home = L.home_dir()
    ledger = home / L.LEDGER_DIRNAME
    if a.cmd == "verify":
        probs = L.verify_chain(home, L.load_manifests(ledger))
        for p in probs:
            print("FAIL", p)
        print("VERIFY OK" if not probs else f"VERIFY FAILED: {len(probs)} problem(s)")
        return 1 if probs else 0
    day = a.day or (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat()
    dt.date.fromisoformat(day)
    rc, res = daily_run(home, day, L.resolve_machine_id(home))
    for d, st in res:
        print(d, st)
    if rc:
        print("CONFLICT: an existing manifest differs from the data now; nothing overwritten. Run `verify`.",
              file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
