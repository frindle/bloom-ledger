"""Frozen test: bloom_ingest.load_tokens treats a machines.json of the wrong shape as empty and never raises."""
import hashlib
import json

import bloom_ingest as I


def h(name):
    return hashlib.sha256(name.encode()).hexdigest()


def load(tmp_path, content):
    secret = tmp_path / "bloom_tokens"
    secret.write_text(f"m1 {h('t1')}\n")
    dyn = tmp_path / "machines.json"
    dyn.write_text(content)
    return I.load_tokens(str(secret), str(dyn))


def test_top_level_not_an_object_is_empty(tmp_path):
    for text in ("[]", "[1, 2]", '"text"', "null", "42", "true"):
        assert load(tmp_path, text) == {h("t1"): "m1"}, text


def test_machines_not_an_object_is_empty(tmp_path):
    for bad in ([], "x", None, 7, [["m2", h("t2")]]):
        assert load(tmp_path, json.dumps({"machines": bad, "revoked": []})) == {h("t1"): "m1"}, bad


def test_revoked_not_a_list_revokes_nothing_and_does_not_raise(tmp_path):
    ok = {"m2": {"hash": h("t2"), "created": 1}}
    for bad in ("m1", None, 5, {"m1": True}):
        assert load(tmp_path, json.dumps({"machines": ok, "revoked": bad})) == {h("t1"): "m1", h("t2"): "m2"}, bad

