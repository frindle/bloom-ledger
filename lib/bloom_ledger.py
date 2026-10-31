#!/usr/bin/env python3
"""Integrity ledger for the Darkbloom bookkeeping data (stdlib only).

Daily manifest = sha256 + byte length of the CLOSED part of every raw file (power-log CSVs, earnings
archive jsonl, totals.jsonl), hash-chained to the previous day's manifest and written append-only to
~/.darkbloom/ledger/manifest-YYYY-MM-DD.json. `verify_chain` walks the chain and re-hashes every file range.
Optional OpenTimestamps stamping of each manifest (`ots` binary; skipped and logged when absent).
Used by bloom-manifest.py. Reads no secrets and writes none. Bookkeeping data, not tax advice
(see docs/bloom-power.md, "Integrity ledger").
"""
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bloom_power_lib as P  # noqa: E402

SCHEMA = 1
GENESIS = "0" * 64
LEDGER_DIRNAME = "ledger"
DEFAULT_MACHINE_ID = "m4max"
RAW_GLOBS = ("power/power-log-*.csv", "earnings-archive/earnings-*.jsonl", "earnings-archive/totals.jsonl")
TS_KEYS = ("_fetched_at", "at")
MANIFEST_RE = re.compile(r"^manifest-(\d{4}-\d{2}-\d{2})\.json$")


# ---------------------------------------------------------------- helpers (fixed contract)
def home_dir():
    return Path(os.environ.get("BLOOM_POWER_HOME") or Path.home() / ".darkbloom")


def _parse_ts(s):
    try:
        d = dt.datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def line_ts(line):
    """Timestamp of one raw line (bytes): the first CSV column (power log `ts_utc`) or the `_fetched_at` / `at`
    key of a JSON line. None for a CSV header or anything unparseable."""
    s = line.decode("utf-8", "replace").strip()
    if s.startswith("{"):
        try:
            d = json.loads(s)
        except ValueError:
            return None
        for k in TS_KEYS:
            if isinstance(d, dict) and d.get(k):
                return _parse_ts(d[k])
        return None
    return _parse_ts(s.split(",", 1)[0])


def day_cutoff(day):
    """End of UTC day 'YYYY-MM-DD' (= next day 00:00:00Z), an aware datetime."""
    d = dt.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    return d + dt.timedelta(days=1)


def days_after(first, last):
    """['YYYY-MM-DD', ...] for every day after `first` up to and including `last`."""
    d, end, out = dt.date.fromisoformat(first), dt.date.fromisoformat(last), []
    while d < end:
        d += dt.timedelta(days=1)
        out.append(d.isoformat())
    return out


def chain_hash(prev_hash, body):
    """sha256 hex of prev_hash + canonical JSON of body (sorted keys, no spaces); a 'chain_hash' key in body is
    ignored, so the stored value can be recomputed from the stored manifest."""
    b = {k: v for k, v in body.items() if k != "chain_hash"}
    blob = json.dumps(b, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((str(prev_hash) + blob).encode()).hexdigest()


def manifest_path(ledger_dir, day):
    return Path(ledger_dir) / f"manifest-{day}.json"


def manifest_bytes(manifest):
    return (json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode()


def _ots_log(ledger_dir, name, action, status, reason=""):
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "manifest": name,
           "action": action, "status": status, "reason": reason}
    P.append_line(Path(ledger_dir) / "ots-status.jsonl", json.dumps(rec, sort_keys=True))


# ---------------------------------------------------------------- closed range + hashing
def closed_length(path, cutoff):
    """Byte length of the closed part of a raw file: up to the end of the last complete line whose timestamp is
    before `cutoff` (aware datetime), stopping at the first complete line at/after it. Lines with no timestamp
    (CSV header) are passed over; a trailing line with no newline is never closed. 0 when the file is missing or
    no timed line is before cutoff."""
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError:
        return 0
    closed = 0
    found = False
    for line in data.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            break
        ts = line_ts(line)
        if ts is None:
            closed += len(line)
            continue
        if ts >= cutoff:
            break
        closed += len(line)
        found = True
    return closed if found else 0


def file_digest(path, nbytes):
    """sha256 hex of the first `nbytes` bytes of a file (read in 1 MiB chunks). None when the file is missing or
    shorter than nbytes."""
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError:
        return None
    if size < int(nbytes):
        return None
    h = hashlib.sha256()
    remaining = int(nbytes)
    chunk = 1 << 20
    try:
        with p.open("rb") as f:
            while remaining > 0:
                take = min(chunk, remaining)
                h.update(f.read(take))
                remaining -= take
    except OSError:
        return None
    return h.hexdigest()



# ---------------------------------------------------------------- manifest
def make_manifest(day, machine_id, files, prev):
    """Manifest dict for UTC day `day`. files: [{'path','bytes','sha256'}]; prev: the previous manifest or None."""
    if prev is not None and prev["date"] >= day:
        raise ValueError("prev must be an EARLIER day")
    body = {
        "schema": SCHEMA,
        "date": day,
        "machine_id": str(machine_id),
        "cutoff_utc": day_cutoff(day).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": sorted(
            [{"path": f["path"], "bytes": int(f["bytes"]), "sha256": f["sha256"]} for f in files],
            key=lambda x: x["path"],
        ),
        "prev_hash": prev["chain_hash"] if prev is not None else GENESIS,
    }
    body["chain_hash"] = chain_hash(body["prev_hash"], body)
    return body


def resolve_machine_id(home, env=None):
    """BLOOM_MACHINE_ID env, else "machine_id" in <home>/ledger.json, else 'm4max'."""
    if env is None:
        env = os.environ
    val = env.get("BLOOM_MACHINE_ID", "")
    stripped = val.strip()
    if stripped:
        return stripped
    ledger_file = Path(home) / "ledger.json"
    try:
        data = json.loads(ledger_file.read_text())
        mid = data.get("machine_id", "")
        if isinstance(mid, str) and mid.strip():
            return mid.strip()
    except Exception:
        pass
    return DEFAULT_MACHINE_ID



# ---------------------------------------------------------------- append-only store
def write_manifest(ledger_dir, manifest):
    """Append-only write of manifest-<date>.json (built in a temp file, then hard-linked into place, so a crash
    never leaves a torn manifest). Returns 'written', 'same' (an identical file is already there: idempotent
    re-run) or 'conflict' (a different file is already there; it is never touched)."""
    target = manifest_path(ledger_dir, manifest["date"])
    ledger_dir = Path(ledger_dir)
    ledger_dir.mkdir(parents=True, exist_ok=True)
    data = manifest_bytes(manifest)
    tmp = ledger_dir / f".{target.name}.tmp{os.getpid()}"
    try:
        tmp.write_bytes(data)
        os.link(tmp, target)
        return "written"
    except FileExistsError:
        if target.read_bytes() == data:
            return "same"
        return "conflict"
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def load_manifests(ledger_dir):
    """[(date from the file name, manifest dict or None when unreadable)] for every manifest-YYYY-MM-DD.json in
    ledger_dir, oldest first. [] when the dir is missing."""
    d = Path(ledger_dir)
    if not d.is_dir():
        return []
    out = []
    for entry in sorted(d.iterdir()):
        m = MANIFEST_RE.match(entry.name)
        if not m:
            continue
        date_str = m.group(1)
        try:
            obj = json.loads(entry.read_text())
            if not isinstance(obj, dict):
                obj = None
        except (OSError, ValueError):
            obj = None
        out.append((date_str, obj))
    return out


# ---------------------------------------------------------------- verify
def verify_files(home, manifest):
    """Problems (strings) found re-hashing one manifest's file ranges against the files under `home` now."""
    problems = []
    date = manifest.get("date")
    for f in manifest.get("files", []):
        digest = file_digest(Path(home) / f["path"], f["bytes"])
        if digest is None:
            problems.append(f"{date} {f['path']}: missing or shorter than {f['bytes']} bytes")
        elif digest != f["sha256"]:
            problems.append(f"{date} {f['path']}: sha256 of the first {f['bytes']} bytes changed")
    return problems


def verify_chain(home, items):
    """Walk load_manifests() output oldest first. Returns a list of problems; [] means every link, chain hash and
    file range verifies."""
    if not items:
        return ["no manifests"]
    problems = []
    prev = None
    prev_day = None
    for day, m in items:
        if m is None:
            problems.append(f"{day}: manifest unreadable")
            prev = None
            prev_day = day
            continue
        # Check date consistency
        if m.get("date") != day:
            problems.append(f"{day}: date mismatch")
        # Check consecutive days
        if prev_day is not None:
            expected = days_after(prev_day, day)
            if expected != [day]:
                problems.append(f"{day}: missing or reordered day")
        # Check prev_hash
        if prev is None:
            expected_prev = GENESIS
        else:
            expected_prev = prev["chain_hash"]
        if m.get("prev_hash") != expected_prev:
            problems.append(f"{day}: prev_hash mismatch")
        # Check chain_hash
        if m.get("chain_hash") != chain_hash(m.get("prev_hash", ""), m):
            problems.append(f"{day}: chain_hash mismatch")
        # Verify files
        problems.extend(verify_files(home, m))
        prev = m
        prev_day = day
    return problems




# ---------------------------------------------------------------- OpenTimestamps
def ots_stamp(manifest_path, ots_bin, run=subprocess.run):
    """Timestamp one manifest with OpenTimestamps (`ots stamp FILE` writes FILE.ots). Never raises.
    Returns 'exists' (FILE.ots already there, nothing run), 'skipped' (ots_bin is None/empty), 'stamped' or
    'failed'. Every outcome except 'exists' appends a line to <manifest dir>/ots-status.jsonl."""
    proof_path = str(manifest_path) + ".ots"
    if Path(proof_path).exists():
        return "exists"
    if not ots_bin:
        _ots_log(Path(manifest_path).parent, Path(manifest_path).name, "stamp", "skipped", "ots binary not found")
        return "skipped"
    try:
        result = run([str(ots_bin), "stamp", str(manifest_path)], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        _ots_log(Path(manifest_path).parent, Path(manifest_path).name, "stamp", "failed", exc.__class__.__name__)
        return "failed"
    if result.returncode == 0 and Path(proof_path).exists():
        _ots_log(Path(manifest_path).parent, Path(manifest_path).name, "stamp", "stamped")
        return "stamped"
    _ots_log(Path(manifest_path).parent, Path(manifest_path).name, "stamp", "failed", f"rc={result.returncode}")
    return "failed"



def ots_upgrade(ledger_dir, ots_bin, run=subprocess.run):
    """For every manifest-*.json oldest first: no FILE.ots yet -> ots_stamp (catches up days stamped while ots was
    missing); else `ots upgrade FILE.ots` -> 'upgraded' (rc 0) or 'pending' (non-zero rc or the run failed).
    Returns {manifest file name: status}. ots_bin None/empty -> {} and nothing is run."""
    if not ots_bin:
        return {}
    result = {}
    ledger_dir = Path(ledger_dir)
    for mf in sorted(ledger_dir.glob("manifest-*.json"), key=lambda x: x.name):
        if not MANIFEST_RE.match(mf.name):
            continue
        proof = Path(str(mf) + ".ots")
        if not proof.exists():
            result[mf.name] = ots_stamp(mf, ots_bin, run)
        else:
            try:
                res = run([str(ots_bin), "upgrade", str(proof)], capture_output=True, text=True, timeout=120)
            except (OSError, subprocess.SubprocessError):
                result[mf.name] = "pending"
                continue
            if res.returncode == 0:
                result[mf.name] = "upgraded"
            else:
                result[mf.name] = "pending"
    return result

