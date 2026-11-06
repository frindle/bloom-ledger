"""Append-only archive of Darkbloom's local records into a content-addressed spool (stdlib only, READ-ONLY toward
Darkbloom: reads files under ~/.darkbloom, never writes there except the spool, never runs the darkbloom CLI).

Why: usage-history.json is a 4096-entry ring (~40 h at current load) and provider.log / lifecycle files are
rewritten or rotated by the provider. Each run copies what is new into ~/.darkbloom/ledger-spool/<kind>/ as
write-once objects named by the sha256 of their bytes; bloom-ship.py pushes them to the Unraid ingest and moves
them to ledger-spool/sent/<kind>/.

Object format: one canonical JSON meta line, b"\\n", then the payload bytes (usage: canonical JSON list of ring
entries; log: the raw appended lines; lifecycle: the file's raw bytes; archive-run: canonical JSON summary).
See the bloom-ledger README."""
import hashlib
import json
import os
import tempfile
from pathlib import Path

import bloom_power_lib as P

SPOOL_DIRNAME = "ledger-spool"
KINDS = ("usage", "log", "lifecycle", "archive-run")
SENT_DIRNAME = "sent"
REJECTED_DIRNAME = "rejected"
SEEN_KEEP = 20000                 # usage ids remembered (the ring holds 4096)
MAX_INCREMENT = 8 * 1024 * 1024   # bytes of one log read per run; the rest follows next run
LOG_GLOBS = ("provider.log", "power/power-log-*.csv", "power/sandbox-jobs-*.csv", "power/net-bytes-*.csv", "power/usage-*.csv", "earnings-archive/*.jsonl")
LIFECYCLE_DIRNAME = "lifecycle"
RING_FILENAME = "usage-history.json"


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def object_bytes(meta, payload):
    return canonical(meta).encode("utf-8") + b"\n" + bytes(payload)


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def split_object(data):
    """(meta dict, payload bytes) of one spool object."""
    head, _, payload = data.partition(b"\n")
    return json.loads(head.decode("utf-8")), payload


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def load_ring(path):
    """The usage-history ring as a list, or None when missing, unreadable, mid-write or not a list."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, list) else None


def log_paths(home):
    """Paths (relative to home, posix) of every append-only log the archiver follows, sorted."""
    home = Path(home)
    out = set()
    for pattern in LOG_GLOBS:
        for p in home.glob(pattern):
            if p.is_file():
                out.add(p.relative_to(home).as_posix())
    return sorted(out)


def new_usage_records(entries, seen):
    """Ring entries not archived yet: dict entries whose "id" is a non-blank str not in `seen`, first occurrence
    of each id only, sorted by (completedAt as a number, 0.0 when not a number, id)."""
    if not isinstance(entries, list):
        return []
    keep = []
    seen_ids = set()
    for e in entries:
        if not isinstance(e, dict):
            continue
        ident = e.get("id")
        if not isinstance(ident, str):
            continue
        if not ident.strip():
            continue
        if ident in seen or ident in seen_ids:
            continue
        seen_ids.add(ident)
        keep.append(e)
    keep.sort(key=lambda e: (_num(e.get("completedAt")), e["id"]))
    return keep


def read_increment(path, st, max_bytes=MAX_INCREMENT):
    """Complete new lines of an append-only file since the last run. st: {"inode", "offset"} from the last run
    ({} the first time). Returns (data, new_st, start_offset)."""
    try:
        s = os.stat(path)
    except OSError:
        return (b"", dict(st or {}), 0)
    if st is None:
        st = {}
    off = st.get("offset", 0)
    if isinstance(off, bool) or not isinstance(off, int) or off < 0:
        off = 0
    elif st.get("inode") != s.st_ino:
        off = 0
    elif s.st_size < off:
        off = 0
    with open(path, "rb") as f:
        f.seek(off)
        data = f.read(max_bytes)
    cut = data.rfind(b"\n")

    if cut < 0:
        return (b"", {"inode": s.st_ino, "offset": off}, off)
    result = data[:cut + 1]
    return (result, {"inode": s.st_ino, "offset": off + len(result)}, off)


def spool_put(spool, kind, meta, payload):
    """Write-once store of one object. Returns (path under spool/<kind>, "written" | "same")."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    spool = Path(spool)
    data = object_bytes(meta, payload)
    name = sha256_hex(data) + ".obj"
    final = spool / kind / name
    # Check if name already exists in spool/kind, spool/sent/kind, or spool/rejected/kind
    for base in (spool, spool / SENT_DIRNAME, spool / REJECTED_DIRNAME):
        candidate = base / kind / name
        if candidate.exists():
            return (final, "same")
    # A mkdir or temp-file error propagates: nothing was stored, so the caller must not advance its state.
    final.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=final.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            fd = -1  # the file object owns (and closes) the descriptor now
            f.write(data)  # buffered write loops over short os.write results
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp, final)
        except FileExistsError:
            if not final.is_file():
                raise
            return (final, "same")  # a concurrent run stored the same bytes (same name) first
    finally:
        if fd >= 0:
            os.close(fd)
        os.unlink(tmp)
    return (final, "written")


def archive_once(home, spool, state, now, machine_id):
    """One archive pass over `home` into `spool`; updates `state` in place. Returns {kind: objects written}."""
    counts = {k: 0 for k in KINDS}

    def put(kind, meta, payload):
        path, status = spool_put(spool, kind, {"machine_id": machine_id, "kind": kind, **meta}, payload)
        if status == "written":
            counts[kind] += 1

    home = Path(home)
    ring = load_ring(home / RING_FILENAME)
    seen = list(state.get("usage_seen") or [])
    new = new_usage_records(ring or [], set(seen))

    if new:
        put("usage", {"source": RING_FILENAME, "count": len(new), "first_id": new[0]["id"], "last_id": new[-1]["id"]}, canonical(new).encode("utf-8"))
        state["usage_seen"] = (seen + [e["id"] for e in new])[-SEEN_KEEP:]

    offsets = state.setdefault("offsets", {})
    for rel in log_paths(home):
        data, new_st, start = read_increment(home / rel, offsets.get(rel) or {})
        if data:
            put("log", {"path": rel, "offset": start, "bytes": len(data)}, data)
        offsets[rel] = new_st

    done = state.setdefault("lifecycle", {})
    for name, raw, digest in lifecycle_changes(home, done):
        put("lifecycle", {"name": name}, raw)
        done[name] = digest

    if ring is not None:
        put("archive-run", {"at": P.utc_iso(now)}, canonical({"at": P.utc_iso(now), "ring_len": len(ring), "new_usage": len(new)}).encode("utf-8"))

    return counts


def lock_and_load_state(spool):
    """(lock file object or None when another run holds it, state dict)."""
    import fcntl
    spool = Path(spool)
    spool.mkdir(parents=True, exist_ok=True)
    os.chmod(spool, 0o700)
    fh = open(spool / ".archive.lock", "a")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None, {}
    try:
        state = json.loads((spool / ".archive-state.json").read_text())
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    return fh, state


def save_state(spool, state):
    """Atomic replace of the state file."""
    spool = Path(spool)
    fd, tmp = tempfile.mkstemp(dir=spool, prefix=".archive-state.")
    with os.fdopen(fd, "w") as f:
        f.write(canonical(state))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, spool / ".archive-state.json")


def log_run(spool, now, counts, error=""):
    rec = {"at": P.utc_iso(now), "counts": counts}
    if error:
        rec["error"] = error
    P.append_line(Path(spool) / "archive.log", canonical(rec))


def lifecycle_changes(home, done):
    """[(name, raw bytes, sha256 hex)] of home/lifecycle/*.json files whose sha256 differs from done.get(name),
    sorted by name. Unreadable files are skipped. Does not modify `done`."""
    out = []
    for p in sorted((Path(home) / LIFECYCLE_DIRNAME).glob("*.json")):
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        digest = sha256_hex(raw)
        if done.get(p.name) != digest:
            out.append((p.name, raw, digest))
    return out
