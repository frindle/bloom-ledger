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
    raise NotImplementedError("not implemented: add_machine")


def rotate_machine(path, machine_id, now):
    raise NotImplementedError("not implemented: rotate_machine")


def revoke_machine(path, machine_id):
    raise NotImplementedError("not implemented: revoke_machine")


def admin_check(headers, secret_path):
    raise NotImplementedError("not implemented: admin_check")


def admin_post(path, headers, body, admin_path, machines_path, now):
    raise NotImplementedError("not implemented: admin_post")


def machine_rows(db, root, now, extra_ids):
    raise NotImplementedError("not implemented: machine_rows")


def ledger_health(db, root, now, version):
    raise NotImplementedError("not implemented: ledger_health")
