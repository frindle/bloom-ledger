"""Daily hash-chained manifests of the objects the ingest received, per machine, reusing bin/bloom_ledger.py
(make_manifest / write_manifest / ots_stamp) so the Mac and Unraid chains have one format and one verifier.

A day's manifest lists every object received that UTC day (server clock), path relative to ROOT:
objects/<machine_id>/<kind>/<sha256>.obj. Objects are write-once and received_at never changes, so a closed day's
manifest is reproducible: a re-run answers "same". `bloom-manifest.py verify` style checking works with
L.verify_chain(ROOT, L.load_manifests(ROOT/ledger/<machine_id>))."""
import subprocess
from pathlib import Path

import bloom_ledger as L

LEDGER_SUBDIR = "ledger"


def ledger_dir(root, machine_id):
    return Path(root) / LEDGER_SUBDIR / machine_id


def machines(db):
    return [r[0] for r in db.execute("SELECT DISTINCT machine_id FROM objects ORDER BY machine_id")]


def day_files(db, machine_id, day):
    """[{'path', 'bytes', 'sha256'}] of the objects machine_id sent on UTC day `day`, sorted by path."""
    rows = db.execute(
        "SELECT kind, sha256, bytes FROM objects WHERE machine_id = ? AND day = ?",
        (machine_id, day)).fetchall()
    return sorted([{"path": f"objects/{machine_id}/{kind}/{sha}.obj", "bytes": int(n), "sha256": sha}
                   for kind, sha, n in rows], key=lambda f: f["path"])


def manifest_run(root, db, day, ots_bin, now, run=subprocess.run):
    """Write (and stamp) day's manifest for every machine. Returns {machine_id: 'written'|'same'|'conflict'}.
    Machines whose ledger already has a later manifest, or whose first object arrived after `day`, are skipped."""
    out = {}
    for mid in machines(db):
        first = db.execute(
            "SELECT MIN(day) FROM objects WHERE machine_id = ?", (mid,)).fetchone()[0]
        if first is None or first > day:
            continue
        ldir = ledger_dir(root, mid)
        prev = None
        skip = False
        for mday, mdict in L.load_manifests(ldir):
            if mdict is not None:
                if mday > day:
                    skip = True
                    break
                if mday < day:
                    prev = mdict
        man = L.make_manifest(day, mid, day_files(db, mid, day), prev)
        st = L.write_manifest(ldir, man)
        out[mid] = st
        if st == "written" and L.ots_stamp(L.manifest_path(ldir, day), ots_bin, run) in ("stamped", "exists"):
            db.execute(
                "INSERT OR IGNORE INTO ots (machine_id, manifest, stamped_at) VALUES (?, ?, ?)",
                (mid, L.manifest_path(ldir, day).name, float(now)))
    db.commit()
    return out
