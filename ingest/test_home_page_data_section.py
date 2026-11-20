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
    assert arts == [] and "Not measured" in box["text"], box["text"]


def whole_label(out):
    arts, _ = tiles(out["dom"])
    return arts[2]["text"], find(out["dom"], "data-note")["text"]


def test_period_labels_say_what_the_whole_machine_figure_counts(tmp_path):
    """Since 2026-11-19 the sampler counts internet traffic only; older minutes include LAN traffic. The tile says which."""
    old, note = whole_label(run(tmp_path, dict(SUM, totals=dict(TOT, net_minutes=2800))))      # no net_internet_minutes
    assert "Whole machine (all traffic incl. LAN)" in old and "local network traffic" in note, (old, note)
    new, note = whole_label(run(tmp_path, dict(SUM, totals=dict(TOT, net_minutes=2800, net_internet_minutes=2800))))
    assert "Whole machine (internet)" in new and "Internet traffic only" in note, (new, note)
    mixed, note = whole_label(run(tmp_path, dict(SUM, totals=dict(TOT, net_minutes=2800, net_internet_minutes=600))))
    assert "Whole machine (mixed)" in mixed and "Mixed: 36.7 h" in note and "10.0 h are internet only" in note, (mixed, note)
