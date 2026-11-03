"""Frozen test: the ledger page has a Data moved section with big per-stream and whole-machine in/out figures. Fake data."""
from dom_support import find, walk
from test_home_page_bandwidth import SUM, TOT, run


def tiles(dom):
    box = find(dom, "data")
    assert box is not None, "no #data section"
    return [n for n in walk(box) if n["tag"] == "article"], box


def test_tiles_show_in_and_out(tmp_path):
    out = run(tmp_path, SUM)
    arts, _ = tiles(out["dom"])
    texts = [a["text"] for a in arts]
    assert len(arts) == 3, texts
    assert "Darkbloom GPU" in texts[0] and "Downloaded" in texts[0] and "1.2 GB" in texts[0] and "45.6 KB" in texts[0], texts[0]
    assert "Sandbox" in texts[1] and "999 B" in texts[1] and "0 B" in texts[1], texts[1]
    assert "Whole machine" in texts[2] and "2.5 TB" in texts[2] and "7.3 MB" in texts[2], texts[2]
    note = find(out["dom"], "data-note")["text"]
    assert "46.7 h of 47.4 h" in note, note


def test_unmeasured_period(tmp_path):
    out = run(tmp_path, dict(SUM, totals=dict(TOT, net_minutes=0)))
    arts, box = tiles(out["dom"])
    assert arts == [] and "Data not measured" in box["text"], box["text"]
