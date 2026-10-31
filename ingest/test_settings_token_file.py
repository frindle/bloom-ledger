"""Frozen test: bloom_settings.read_machines / write_machines (the dynamic machines.json)."""
import hashlib
import json
import os
import stat

import bloom_settings as S

EMPTY = {"machines": {}, "revoked": []}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def test_read_machines_defaults_and_roundtrip(tmp_path):
    p = tmp_path / "machines.json"
    assert S.read_machines(str(p)) == EMPTY, "missing file"
    p.write_text("{not json")
    assert S.read_machines(str(p)) == EMPTY, "corrupt file"
    p.write_text('["list"]')
    assert S.read_machines(str(p)) == EMPTY, "wrong shape"
    data = {"machines": {"m1": {"hash": sha("t"), "created": 5.0}}, "revoked": ["m9"]}
    p.write_text(json.dumps(data))
    assert S.read_machines(str(p)) == data


def test_write_machines_is_private_and_atomic(tmp_path):
    p = tmp_path / "machines.json"
    p.write_text("{}")
    os.chmod(p, 0o644)
    data = {"machines": {"m1": {"hash": sha("t"), "created": 5.0}}, "revoked": []}
    S.write_machines(str(p), data)
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    assert json.loads(p.read_text()) == data
    fresh = tmp_path / "sub.json"
    S.write_machines(str(fresh), EMPTY)
    assert stat.S_IMODE(os.stat(fresh).st_mode) == 0o600
    assert sorted(x.name for x in tmp_path.iterdir()) == ["machines.json", "sub.json"], "no temp files left"
