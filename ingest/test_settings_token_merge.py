"""Frozen test: bloom_ingest.load_tokens merges the read-only secret file with the dynamic machines.json."""
import hashlib
import json

import bloom_ingest as I


def h(name):
    return hashlib.sha256(name.encode()).hexdigest()


def write_secret(tmp_path, pairs):
    p = tmp_path / "bloom_tokens"
    p.write_text("".join(f"{mid} {digest}\n" for mid, digest in pairs))
    return str(p)


def write_machines(tmp_path, machines=None, revoked=None):
    p = tmp_path / "machines.json"
    p.write_text(json.dumps({"machines": machines or {}, "revoked": revoked or []}))
    return str(p)


def test_dynamic_machines_are_merged(tmp_path):
    secret = write_secret(tmp_path, [("m1", h("t1"))])
    dyn = write_machines(tmp_path, {"m2": {"hash": h("t2"), "created": 1.0}})
    assert I.load_tokens(secret, dyn) == {h("t1"): "m1", h("t2"): "m2"}
    assert I.load_tokens(secret) == {h("t1"): "m1"}, "no machines_path means the secret file alone"


def test_secret_file_wins_conflicts(tmp_path):
    secret = write_secret(tmp_path, [("m1", h("t1")), ("m2", h("t2"))])
    dyn = write_machines(tmp_path, {"m1": {"hash": h("other"), "created": 1.0},
                                    "m9": {"hash": h("t2"), "created": 1.0},
                                    "m3": {"hash": h("t3"), "created": 1.0}})
    got = I.load_tokens(secret, dyn)
    assert got == {h("t1"): "m1", h("t2"): "m2", h("t3"): "m3"}, got


def test_revoked_ids_are_dropped_from_both_sources(tmp_path):
    secret = write_secret(tmp_path, [("m1", h("t1")), ("m2", h("t2"))])
    dyn = write_machines(tmp_path, {"m3": {"hash": h("t3"), "created": 1.0},
                                    "m4": {"hash": h("t4"), "created": 1.0}}, revoked=["m2", "m4"])
    assert I.load_tokens(secret, dyn) == {h("t1"): "m1", h("t3"): "m3"}


def test_bad_entries_and_corrupt_file_are_skipped(tmp_path):
    secret = write_secret(tmp_path, [("m1", h("t1"))])
    dyn = write_machines(tmp_path, {"m5": {"hash": h("t5").upper(), "created": 1.0},
                                    "m6": {"hash": "not-a-hash", "created": 1.0},
                                    "bad id!": {"hash": h("t7"), "created": 1.0},
                                    "m8": "oops"})
    assert I.load_tokens(secret, dyn) == {h("t1"): "m1", h("t5"): "m5"}
    (tmp_path / "machines.json").write_text("{not json")
    assert I.load_tokens(secret, str(tmp_path / "machines.json")) == {h("t1"): "m1"}


def test_missing_secret_file_still_loads_machines(tmp_path):
    dyn = write_machines(tmp_path, {"m6": {"hash": h("t6"), "created": 1.0}})
    assert I.load_tokens(str(tmp_path / "absent"), dyn) == {h("t6"): "m6"}
    assert I.load_tokens(str(tmp_path / "absent"), str(tmp_path / "absent2")) == {}
