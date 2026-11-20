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


def test_whole_machine_is_internet_only(tmp_path):
    """Data moved is internet only. Older all-traffic minutes are left out and the note says how many."""
    new, note = whole_label(run(tmp_path, dict(SUM, totals=dict(TOT, net_minutes=2800))))
    assert "Whole machine (internet)" in new and "Internet traffic only" in note and "left out" not in note, (new, note)
    mixed, note = whole_label(run(tmp_path, dict(SUM, totals=dict(TOT, net_minutes=600, net_legacy_minutes=2200))))
    assert "Whole machine (internet)" in mixed and "Internet traffic only" in note, (mixed, note)
    assert "36.7 h recorded before internet-only counting" in note and "left out" in note, note
    assert "incl. LAN" not in mixed and "mixed" not in mixed.lower(), mixed


def test_a_period_with_only_older_minutes_shows_no_figures(tmp_path):
    out = run(tmp_path, dict(SUM, totals=dict(TOT, net_minutes=0, net_legacy_minutes=2800)))
    arts, box = tiles(out["dom"])
    assert arts == [] and "Not counted" in box["text"] and "46.7 h recorded before" in box["text"], box["text"]
    assert " TB" not in box["text"] and " GB" not in box["text"], box["text"]
