"""Frozen test: bloom_settings.add_machine (the dynamic machines.json)."""
import hashlib
import json
import os
import stat

import pytest

import bloom_ingest as I
import bloom_settings as S

EMPTY = {"machines": {}, "revoked": []}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def test_add_machine_returns_token_and_stores_only_its_hash(tmp_path):
    p = str(tmp_path / "machines.json")
    tok = S.add_machine(p, "m1", 123.0)
    tok2 = S.add_machine(p, "m2", 124.0)
    assert isinstance(tok, str) and len(tok) >= 32 and tok != tok2
    text = open(p).read()
    assert tok not in text and tok2 not in text, "plaintext token must never be stored"
    data = json.loads(text)
    assert data["machines"]["m1"] == {"hash": sha(tok), "created": 123.0}
    assert data["machines"]["m2"]["hash"] == sha(tok2)
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    assert I.load_tokens(str(tmp_path / "absent"), p) == {sha(tok): "m1", sha(tok2): "m2"}


def test_add_machine_rejects_bad_and_duplicate_ids(tmp_path):
    p = str(tmp_path / "machines.json")
    for bad in ["", "bad id!", "-x", "a" * 65, "../x"]:
        with pytest.raises(ValueError):
            S.add_machine(p, bad, 1.0)
    assert not os.path.exists(p), "a refused id writes nothing"
    tok = S.add_machine(p, "m1", 1.0)
    with pytest.raises(ValueError):
        S.add_machine(p, "m1", 2.0)
    assert json.load(open(p))["machines"]["m1"]["hash"] == sha(tok), "the first token survives a duplicate add"


def test_add_machine_reenables_a_revoked_id(tmp_path):
    p = tmp_path / "machines.json"
    p.write_text(json.dumps({"machines": {}, "revoked": ["m1", "m2"]}))
    tok = S.add_machine(str(p), "m1", 9.0)
    data = json.loads(p.read_text())
    assert data["revoked"] == ["m2"], data
    assert data["machines"]["m1"]["hash"] == sha(tok)
