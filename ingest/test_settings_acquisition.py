"""Frozen test: switching a machine row between Leased and Purchased swaps its visible labels and its stored values. Fake data."""
import json

import dom_support as D

LEASE = {"display_name": "Studio", "model": "M4 Max", "acquisition": "leased", "lease_start": "2026-01-15",
         "lease_monthly_cents": 12345, "in_service": "2026-09-28", "purchase_cents": 322565}


def page(tmp_path, profile, steps=None):
    machines = [{"id": "m4max", "last_seen": 1793299880, "objects": 5, "days_sealed": 2, "status": "reporting", "profile": profile}]
    fx = {"/v1/settings": {"status": 200, "body": {"machines": machines, "health": {"time": 1793300000}}},
          "POST /v1/settings/machines/profile": {"status": 200, "body": {"ok": True}}}
    res = D.run_page(tmp_path, fx, steps)
    assert res["errors"] == [], res["errors"]
    return res


def shown(res):
    def v(i):
        n = D.find(res["dom"], i)
        assert n is not None, "no element " + i
        return n
    return (v("start-label-m4max")["text"], v("start-m4max")["value"], v("amt-label-m4max")["text"], v("amt-m4max")["value"])


def to(mode):
    return {"do": "change", "id": "acq-m4max", "values": {"acq-m4max": mode}}


def test_labels_follow_the_loaded_mode(tmp_path):
    assert shown(page(tmp_path, LEASE)) == ("Lease start", "2026-01-15", "Per month", "123.45")
    assert shown(page(tmp_path, dict(LEASE, acquisition="purchased"))) == ("In service", "2026-09-28", "Purchase price", "3225.65")


def test_switching_loads_the_other_modes_values(tmp_path):
    res = page(tmp_path, LEASE, [to("purchased")])
    assert shown(res) == ("In service", "2026-09-28", "Purchase price", "3225.65")
    assert D.find(res["dom"], "start-m4max")["attrs"]["aria-label"] == "In service date for m4max"
    back = page(tmp_path, LEASE, [to("purchased"), to("leased")])
    assert shown(back) == ("Lease start", "2026-01-15", "Per month", "123.45")


def test_switching_to_an_empty_mode_clears_the_fields(tmp_path):
    res = page(tmp_path, dict(LEASE, in_service=None, purchase_cents=None), [to("purchased")])
    assert shown(res) == ("In service", "", "Purchase price", "")


def test_edits_survive_a_round_trip(tmp_path):
    steps = [{"do": "input", "id": "amt-m4max", "values": {"amt-m4max": "99.00"}}, to("purchased"), to("leased")]
    assert shown(page(tmp_path, LEASE, steps))[3] == "99.00"


def test_save_after_switching_posts_the_purchase(tmp_path):
    res = page(tmp_path, dict(LEASE, in_service=None, purchase_cents=None),
               [to("purchased"), {"do": "input", "id": "start-m4max", "values": {"start-m4max": "2026-09-28", "amt-m4max": "3225.65"}},
                {"do": "click", "sel": ".primary"}])
    (post,) = [f for f in res["fetches"] if f["method"] == "POST"]
    body = json.loads(post["body"])
    assert body["acquisition"] == "purchased" and body["in_service"] == "2026-09-28" and body["purchase_cents"] == 322565
    assert body["lease_start"] is None and body["lease_monthly_cents"] is None
