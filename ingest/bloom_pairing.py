"""Plug-and-play setup for a new Mac: single-use pairing codes, the one-line installer and the client bundle.

Flow: Settings > Add a machine creates the machine (token) and a pairing code good for PAIR_TTL_S. The page shows
    curl -fsSL http://<ledger>:8787/install.sh | sh -s -- --pair <code>
On the Mac, install.sh downloads /client.tar.gz, redeems the code at POST /v1/pair for the machine id and token, stores
the token in the login Keychain and loads the LaunchAgents. Codes live in memory only (a restart forgets them; make a
new one with New token). The server id lets a Mac find the ledger again if its address changes (GET /v1/hello)."""
import hashlib
import io
import json
import os
import re
import secrets
import tarfile
import threading
from pathlib import Path

PAIR_TTL_S = 30 * 60
CODE_RE = re.compile(r"^[A-Za-z0-9_-]{12,64}$")
HOST_RE = re.compile(r"^[A-Za-z0-9.\-]{1,253}(:[0-9]{1,5})?$|^\[[0-9A-Fa-f:.]+\](:[0-9]{1,5})?$")
_HERE = Path(__file__).resolve().parent
CLIENT_DIR = Path(os.environ.get("BLOOM_CLIENT_DIR") or (_HERE / "client" if (_HERE / "client").is_dir() else _HERE.parent / "client"))
LIB_FILES = ("bloom_power_lib.py", "bloom_ledger.py", "bloom-earnings-archive.py", "bloom-manifest.py")
LIB_DIR = Path(os.environ.get("BLOOM_LIB_DIR") or (_HERE if (_HERE / "bloom_ledger.py").is_file() else _HERE.parent / "lib"))
_codes = {}
_lock = threading.Lock()


def new_code(machine_id, token, now):
    """A fresh single-use code for (machine_id, token); older codes for that machine stop working."""
    code = secrets.token_urlsafe(12)
    with _lock:
        for c in [c for c, v in _codes.items() if v["id"] == machine_id or v["exp"] <= now]:
            del _codes[c]
        _codes[code] = {"id": machine_id, "token": token, "exp": now + PAIR_TTL_S}
    return code


def forget(machine_id):
    with _lock:
        for c in [c for c, v in _codes.items() if v["id"] == machine_id]:
            del _codes[c]


def redeem(body, now, server_id):
    """POST /v1/pair: {"code"} -> (200, {machine_id, token, server_id}) once; 404 for an unknown, used or expired code."""
    try:
        data = json.loads(body)
        code = data.get("code") if isinstance(data, dict) else None
    except ValueError:
        code = None
    if not isinstance(code, str) or not CODE_RE.match(code):
        return 400, {"error": "send {\"code\": ...}"}
    with _lock:
        v = _codes.pop(code, None)
    if v is None or v["exp"] <= now:
        return 404, {"error": "that pairing code is unknown, used or expired: make a new one in Settings"}
    return 200, {"machine_id": v["id"], "token": v["token"], "server_id": server_id}


def server_id(root):
    """A random id for this ledger, created once under the data folder."""
    p = Path(root) / "server_id"
    try:
        sid = p.read_text().strip()
        if re.fullmatch(r"[0-9a-f]{32}", sid):
            return sid
    except OSError:
        pass
    sid = secrets.token_hex(16)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(sid + "\n")
    os.replace(tmp, p)
    return sid


def client_files(client_dir=None, lib_dir=None):
    """(name in the bundle, path) for every client file plus the shared libraries the Mac scripts import."""
    d = Path(client_dir or CLIENT_DIR)
    out = {p.relative_to(d).as_posix(): p for p in d.rglob("*")
           if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith(".")}
    for name in LIB_FILES:
        lp = Path(lib_dir or LIB_DIR) / name
        if lp.is_file():
            out.setdefault(name, lp)
    return sorted(out.items())


def client_bundle(client_dir=None, lib_dir=None):
    """The Mac client as a deterministic .tar.gz (same bytes for the same files) under bloom-ledger-client/."""
    buf = io.BytesIO()
    import gzip
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for name, p in client_files(client_dir, lib_dir):
                data = p.read_bytes()
                info = tarfile.TarInfo("bloom-ledger-client/" + name)
                info.size, info.mtime, info.uid, info.gid, info.uname, info.gname = len(data), 0, 0, 0, "", ""
                info.mode = 0o755 if os.access(p, os.X_OK) or p.suffix in (".sh",) else 0o644
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def client_version(client_dir=None, lib_dir=None):
    """Short sha256 over the client's file names and bytes (what the Mac reports as its client version)."""
    h = hashlib.sha256()
    for name, p in client_files(client_dir, lib_dir):
        h.update(name.encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()[:12]


def install_script(host_header, client_dir=None):
    """install.sh with this ledger's address filled in from the request's Host header; None for a bad Host."""
    host = (host_header or "").strip()
    if not HOST_RE.match(host):
        return None
    tpl = (Path(client_dir or CLIENT_DIR) / "install.sh").read_text()
    return tpl.replace("@@LEDGER_BASE@@", "http://" + host)


def requested_key(path, body):
    """The optional "darkbloom_key" sent with Add a machine (a str), else None. Not validated here."""
    if path != "/v1/settings/machines":
        return None
    try:
        data = json.loads(body)
    except ValueError:
        return None
    k = data.get("darkbloom_key") if isinstance(data, dict) else None
    return k.strip() if isinstance(k, str) and k.strip() else None


def after_machine_change(path, code, obj, body, dbkey, root, now):
    """Side effects of a successful machine change, and the reply to send: a new or rotated token also gets a pairing
    code; a key sent with Add a machine is saved for that machine; removing a machine forgets its key and codes."""
    import bloom_accounting_live as LV
    if code not in (200, 201) or not isinstance(obj, dict):
        return obj
    if path in ("/v1/settings/machines", "/v1/settings/machines/rotate") and obj.get("token"):
        mid = obj["id"]
        if dbkey is not None:
            LV.set_machine_key(root, mid, dbkey)
        return dict(obj, pair_code=new_code(mid, obj["token"], now), pair_ttl_s=PAIR_TTL_S,
                    darkbloom_key_saved=bool(dbkey) or mid in LV.read_machine_keys(root))
    if path in ("/v1/settings/machines/remove", "/v1/settings/machines/revoke"):
        try:
            mid = json.loads(body).get("id")
        except (ValueError, AttributeError):
            mid = None
        if isinstance(mid, str):
            forget(mid)
            LV.set_machine_key(root, mid, None)
    return obj
