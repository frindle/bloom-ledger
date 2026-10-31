"""bloom-ledger ingest: content-addressed object store + SQLite index (stdlib only, runs in the Unraid container).

Layout under ROOT (the /data volume):
  objects/<machine_id>/<kind>/<sha256>.obj   write-once, exactly the bytes the Mac spooled
  ledger/<machine_id>/manifest-<day>.json    daily hash-chained manifests, bloom_ingest_ledger.py
  index.sqlite                               objects table
Tokens: /run/secrets/bloom_tokens, one "<machine_id> <sha256 hex of the token>" per line. Only hashes are stored;
a token is never logged."""
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path

KINDS = ("usage", "log", "lifecycle", "archive-run")
MAX_BYTES = 32 * 1024 * 1024
SHA_RE = re.compile(r"^[0-9a-f]{64}\Z")
MID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")

SCHEMA = """
CREATE TABLE IF NOT EXISTS objects (
  machine_id TEXT NOT NULL, kind TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
  received_at REAL NOT NULL, day TEXT NOT NULL, PRIMARY KEY (machine_id, sha256));
CREATE INDEX IF NOT EXISTS objects_day ON objects (machine_id, day);
"""


def open_db(path):
    db = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    return db


def utc_day(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")


def load_tokens(path, machines_path=None):
    """{sha256 hex of token: machine_id} from the tokens file; bad lines are skipped. {} when missing.
    machines_path (optional): the dynamic machines.json, see bloom_settings.py (not merged yet)."""
    out = {}
    try:
        text = Path(path).read_text()
    except OSError:
        pass
    else:
        for line in text.splitlines():
            parts = line.split()
            if len(parts) == 2 and not parts[0].startswith("#") and MID_RE.match(parts[0]) and SHA_RE.match(parts[1].lower()):
                out[parts[1].lower()] = parts[0]
    if machines_path:
        try:
            data = json.loads(Path(machines_path).read_text())
            if not isinstance(data, dict):
                return out
            raw_revoked = data.get("revoked", [])
            revoked = set()
            if isinstance(raw_revoked, list):
                for r in raw_revoked:
                    if isinstance(r, str):
                        revoked.add(r)
            out = {sha: mid for sha, mid in out.items() if mid not in revoked}
            machines = data.get("machines", {})
            if isinstance(machines, dict):
                for mid, info in machines.items():
                    if mid in revoked:
                        continue
                    if not isinstance(info, dict):
                        continue
                    h = info.get("hash")
                    if not isinstance(h, str) or not SHA_RE.match(h.lower()):
                        continue
                    if not MID_RE.match(mid):
                        continue
                    hlow = h.lower()
                    if mid not in set(out.values()) and hlow not in out:
                        out[hlow] = mid
        except (OSError, ValueError, TypeError, KeyError):
            pass
    return out


def token_machine(headers, tokens):
    """machine_id for the request's bearer token, or None."""
    auth = headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        return None
    tok = auth[len("Bearer "):].strip()
    if not tok:
        return None
    digest = hashlib.sha256(tok.encode("utf-8")).hexdigest()
    found = None
    for stored, mid in tokens.items():  # constant-time compare against every stored hash line
        if hmac.compare_digest(stored, digest) and found is None:
            found = mid
    return found


def store_object(root, machine_id, kind, sha, body):
    """Write-once store. Returns (path, "written" | "exists"); ValueError on a bad id/kind/sha or mismatch."""
    if kind not in KINDS:
        raise ValueError("bad machine_id, kind or sha256")
    if not isinstance(sha, str) or not SHA_RE.match(sha):
        raise ValueError("bad machine_id, kind or sha256")
    if not MID_RE.match(str(machine_id)):
        raise ValueError("bad machine_id, kind or sha256")
    if hashlib.sha256(body).hexdigest() != sha:
        raise ValueError("sha256 mismatch")
    final = Path(root) / "objects" / machine_id / kind / f"{sha}.obj"
    if final.exists():
        return (final, "exists")
    final.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(final.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            fd = -1  # the file object owns (and closes) the descriptor now
            f.write(body)  # buffered write loops over short os.write results
            f.flush()
            os.fsync(f.fileno())
        os.link(tmp, str(final))
    except FileExistsError:
        return (final, "exists")
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return (final, "written")


def index_object(db, machine_id, kind, sha, nbytes, received_at):
    """Record one object (first receipt wins). Returns True when a new row was added."""
    cur = db.execute(
        "INSERT OR IGNORE INTO objects (machine_id, kind, sha256, bytes, received_at, day) VALUES (?, ?, ?, ?, ?, ?)",
        (machine_id, kind, sha, int(nbytes), float(received_at), utc_day(received_at)),
    )
    db.commit()
    return cur.rowcount == 1


def handle_post(headers, body, tokens, root, db, now):
    """POST /v1/objects. Returns (http status, json-able dict)."""
    mid = token_machine(headers, tokens)
    if mid is None:
        return 401, {"error": "unauthorized"}
    if len(body) > MAX_BYTES:
        return 413, {"error": "too large"}
    kind = headers.get("X-Bloom-Kind") or ""
    sha = (headers.get("X-Bloom-Sha256") or "").strip().lower()
    if kind not in KINDS or not SHA_RE.match(sha):
        return 400, {"error": "bad kind or sha256"}
    if hashlib.sha256(body).hexdigest() != sha:
        return 422, {"error": "sha256 mismatch"}
    path, st = store_object(root, mid, kind, sha, body)
    index_object(db, mid, kind, sha, len(body), now)
    return (201 if st == "written" else 200), {"sha256": sha, "status": st}


def healthz(root, db):
    """(200, {...}) when the volume is writable and the index answers, else (503, {...})."""
    try:
        n = db.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
        fd, tmp = tempfile.mkstemp(dir=str(root), prefix=".health-")
        os.close(fd)
        os.unlink(tmp)
    except (OSError, sqlite3.Error) as e:
        return 503, {"ok": False, "error": type(e).__name__}
    return 200, {"ok": True, "objects": n}
