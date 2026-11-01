"""Frozen test: Settings page per-machine acquisition toggle and content-sized inputs."""
import json
from pathlib import Path

import dom_support as D
from test_settings_page import PROFILE, load, one, post_calls

HERE = Path(__file__).resolve().parent


def acq_select(res, mid="m4max"):
    return D.find(res["dom"], "acq-" + mid)


def test_acquisition_toggle_defaults_to_leased_and_lists_both_options(tmp_path):
    res = load(tmp_path, one())
    sel = acq_select(res)
    assert sel["tag"] == "select" and sel["value"] == "leased"
    assert [o["attrs"].get("value") for o in sel["children"]] == ["leased", "purchased"]
    assert [o["text"] for o in sel["children"]] == ["Leased", "Purchased"]
    assert "m4max" in sel["attrs"]["aria-label"]
    res = load(tmp_path, one(dict(PROFILE, acquisition="purchased")))
    assert acq_select(res)["value"] == "purchased"


def test_changing_the_toggle_is_saved_with_the_row(tmp_path):
    steps = [{"do": "change", "id": "acq-m4max", "values": {"acq-m4max": "purchased"}}, {"do": "click", "sel": ".primary"}]
    res = load(tmp_path, one(), steps, **{"/profile": (200, {"ok": True})})
    assert res["errors"] == [], res["errors"]
    (post,) = post_calls(res)
    assert json.loads(post["body"])["acquisition"] == "purchased"


def text_size(res, input_id):
    return int(D.find(res["dom"], input_id)["attrs"]["size"])


def test_text_inputs_are_sized_to_their_content_with_min_and_max(tmp_path):
    long_model = "M4 Max 64GB " + "x" * 48
    res = load(tmp_path, one(dict(PROFILE, model="M4 Max 64GB", display_name=None)))
    assert text_size(res, "model-m4max") >= len("M4 Max 64GB") + 2, "never narrower than the text"
    assert 8 <= text_size(res, "name-m4max") <= 12, "an empty field keeps a sensible minimum"
    res = load(tmp_path, one(dict(PROFILE, model=long_model)))
    assert 24 <= text_size(res, "model-m4max") <= 40, "long values are capped"
    steps = [{"do": "input", "id": "model-m4max", "values": {"model-m4max": "M4 Max 64GB 1TB unified"}}]
    res = load(tmp_path, one(), steps)
    assert text_size(res, "model-m4max") >= len("M4 Max 64GB 1TB unified") + 2, "typing grows the field"
