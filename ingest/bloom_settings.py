"""bloom-ledger settings: dynamic machine tokens, admin auth and the settings view (stdlib only).

Dynamic tokens live in <data>/machines.json (mode 0600, hashes only, never a plaintext token):
  {"machines": {"<id>": {"hash": "<sha256 hex of the token>", "created": <unix time>}}, "revoked": ["<id>", ...]}
The read-only docker secret bloom_tokens stays the base set; bloom_ingest.load_tokens merges both.
Admin writes need the secret /run/secrets/bloom_admin sent as a Bearer token. Nothing here logs a token or a body."""


def read_machines(path):
    try:
        import json
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"machines": {}, "revoked": []}
        machines = data.get("machines", {})
        revoked = data.get("revoked", [])
        if not isinstance(machines, dict):
            machines = {}
        if not isinstance(revoked, list):
            revoked = []
        else:
            revoked = [r for r in revoked if isinstance(r, str)]
        return {"machines": machines, "revoked": revoked}
    except Exception:
        return {"machines": {}, "revoked": []}


def write_machines(path, data):
    import json
    import os
    import tempfile
    dirn = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=dirn, suffix=".tmp")
    try:
        os.write(fd, json.dumps(data).encode())
        os.close(fd)
        fd = -1
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        try:
            if fd >= 0:
                os.close(fd)
        except Exception:
            pass
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def add_machine(path, machine_id, now):
    import hashlib
    import json
    import secrets
    import bloom_ingest
    if not isinstance(machine_id, str) or not bloom_ingest.MID_RE.match(machine_id):
        raise ValueError(f"invalid machine_id: {machine_id!r}")
    data = read_machines(path)
    if machine_id in data["machines"]:
        raise ValueError(f"duplicate machine_id: {machine_id!r}")
    token = secrets.token_urlsafe(32)
    h = hashlib.sha256(token.encode()).hexdigest()
    data["machines"][machine_id] = {"hash": h, "created": now}
    if machine_id in data["revoked"]:
        data["revoked"].remove(machine_id)
    write_machines(path, data)
    return token


def rotate_machine(path, machine_id, now):
    import hashlib
    import json
    import secrets
    import bloom_ingest
    if not isinstance(machine_id, str) or not bloom_ingest.MID_RE.match(machine_id):
        raise ValueError(f"invalid machine_id: {machine_id!r}")
    data = read_machines(path)
    if machine_id not in data["machines"]:
        raise ValueError(f"unknown machine_id: {machine_id!r}")
    token = secrets.token_urlsafe(32)
    h = hashlib.sha256(token.encode()).hexdigest()
    data["machines"][machine_id]["hash"] = h
    data["machines"][machine_id]["rotated"] = now
    write_machines(path, data)
    return token


def revoke_machine(path, machine_id):
    import json
    import bloom_ingest
    if not isinstance(machine_id, str) or not bloom_ingest.MID_RE.match(machine_id):
        raise ValueError(f"invalid machine_id: {machine_id!r}")
    data = read_machines(path)
    if machine_id in data["machines"]:
        del data["machines"][machine_id]
    if machine_id not in data["revoked"]:
        data["revoked"].append(machine_id)
    data["revoked"] = sorted(set(data["revoked"]))
    write_machines(path, data)
    return None


def admin_check(headers, secret_path):
    import hashlib
    import hmac
    import os
    import re
    try:
        secret = open(secret_path).read().strip()
    except Exception:
        return (403, {"error": "admin disabled"})
    if not secret:
        return (403, {"error": "admin disabled"})
    auth = headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return (401, {"error": "unauthorized"})
    token = auth[7:].strip()
    if not token:
        return (401, {"error": "unauthorized"})
    secret_lower = secret.lower()
    is_64_hex = bool(re.fullmatch(r"[0-9a-f]{64}", secret_lower))
    if is_64_hex:
        if hmac.compare_digest(token.encode(), secret.encode()):
            return None
        if hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest().encode(), secret_lower.encode()):
            return None
    else:
        if hmac.compare_digest(token.encode(), secret.encode()):
            return None
        if hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest().encode(), secret_lower.encode()):
            return None
    return (401, {"error": "unauthorized"})


def admin_post(path, headers, body, admin_path, machines_path, now):
    import json
    import bloom_ingest
    result = admin_check(headers, admin_path)
    if result is not None:
        return result
    if path == "/v1/settings/machines":
        try:
            data = json.loads(body)
        except Exception:
            return (400, {"error": "bad request"})
        if not isinstance(data, dict):
            return (400, {"error": "bad request"})
        mid = data.get("id")
        if not isinstance(mid, str) or not bloom_ingest.MID_RE.match(mid):
            return (400, {"error": "bad request"})
        try:
            token = add_machine(machines_path, mid, now)
        except ValueError:
            return (409, {"error": "machine exists"})
        return (201, {"id": mid, "token": token})
    elif path == "/v1/settings/machines/rotate":
        try:
            data = json.loads(body)
        except Exception:
            return (400, {"error": "bad request"})
        if not isinstance(data, dict):
            return (400, {"error": "bad request"})
        mid = data.get("id")
        if not isinstance(mid, str) or not bloom_ingest.MID_RE.match(mid):
            return (400, {"error": "bad request"})
        try:
            token = rotate_machine(machines_path, mid, now)
        except ValueError:
            return (404, {"error": "unknown machine"})
        return (200, {"id": mid, "token": token})
    elif path == "/v1/settings/machines/revoke":
        try:
            data = json.loads(body)
        except Exception:
            return (400, {"error": "bad request"})
        if not isinstance(data, dict):
            return (400, {"error": "bad request"})
        mid = data.get("id")
        if not isinstance(mid, str) or not bloom_ingest.MID_RE.match(mid):
            return (400, {"error": "bad request"})
        revoke_machine(machines_path, mid)
        return (200, {"id": mid, "revoked": True})
    else:
        return (404, {"error": "not found"})


def machine_rows(db, root, now, extra_ids):
    raise NotImplementedError("not implemented: machine_rows")


def ledger_health(db, root, now, version):
    raise NotImplementedError("not implemented: ledger_health")
