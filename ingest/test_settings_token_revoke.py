"""Frozen test: bloom_settings.rotate_machine / revoke_machine."""
import hashlib
import json
import os
import stat

import pytest

import bloom_ingest as I
import bloom_settings as S


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def test_rotate_replaces_the_hash_and_keeps_created(tmp_path):
    p = str(tmp_path / "machines.json")
    old = S.add_machine(p, "m1", 100.0)
    new = S.rotate_machine(p, "m1", 200.0)
    assert isinstance(new, str) and new != old and len(new) >= 32
    ent = json.load(open(p))["machines"]["m1"]
    assert ent["hash"] == sha(new) and ent["created"] == 100.0 and ent["rotated"] == 200.0, ent
    assert I.load_tokens(str(tmp_path / "absent"), p) == {sha(new): "m1"}, "the old hash is gone"
    assert new not in open(p).read()
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_rotate_unknown_or_invalid_id_raises_and_writes_nothing(tmp_path):
    p = str(tmp_path / "machines.json")
    S.add_machine(p, "m1", 1.0)
    before = open(p).read()
    for bad in ["m2", "bad id!", ""]:
        with pytest.raises(ValueError):
            S.rotate_machine(p, bad, 2.0)
    assert open(p).read() == before


def test_revoke_moves_a_dynamic_machine_to_the_revoked_list(tmp_path):
    p = str(tmp_path / "machines.json")
    tok = S.add_machine(p, "m1", 1.0)
    S.add_machine(p, "m2", 1.0)
    assert S.revoke_machine(p, "m1") is None
    data = json.load(open(p))
    assert "m1" not in data["machines"] and "m2" in data["machines"] and data["revoked"] == ["m1"], data
    assert sha(tok) not in I.load_tokens(str(tmp_path / "absent"), p)


def test_revoke_also_cuts_off_a_secret_file_machine(tmp_path):
    secret = tmp_path / "bloom_tokens"
    secret.write_text(f"studio {sha('t1')}\nm2 {sha('t2')}\n")
    p = str(tmp_path / "machines.json")
    S.revoke_machine(p, "studio")
    assert json.load(open(p))["revoked"] == ["studio"]
    assert I.load_tokens(str(secret), p) == {sha("t2"): "m2"}


def test_revoke_is_idempotent_sorted_and_validates_the_id(tmp_path):
    p = str(tmp_path / "machines.json")
    S.revoke_machine(p, "zeta")
    S.revoke_machine(p, "alpha")
    S.revoke_machine(p, "zeta")
    assert json.load(open(p))["revoked"] == ["alpha", "zeta"]
    with pytest.raises(ValueError):
        S.revoke_machine(p, "bad id!")
    assert json.load(open(p))["revoked"] == ["alpha", "zeta"]
