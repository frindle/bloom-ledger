"""Frozen test: bloom_ingest.store_object and bloom_ingest.index_object. Fixture ids only."""
import hashlib
import os

import pytest

import bloom_ingest as I

NOW = 1793300000.0   # 2026-10-29T18:53:20Z


def sha(b):
    return hashlib.sha256(b).hexdigest()


def test_store_object_write_once(tmp_path):
    body = b'{"k":"log"}\nline\n'
    p, st = I.store_object(tmp_path, "m4max", "log", sha(body), body)
    assert st == "written" and p == tmp_path / "objects" / "m4max" / "log" / f"{sha(body)}.obj"
    assert p.read_bytes() == body
    p2, st2 = I.store_object(tmp_path, "m4max", "log", sha(body), body)
    assert (p2, st2) == (p, "exists")
    assert os.listdir(p.parent) == [p.name], "no temp files left behind"
    p3, st3 = I.store_object(tmp_path, "m5ultra", "log", sha(body), body)
    assert st3 == "written" and p3 != p, "each machine has its own namespace"


@pytest.mark.parametrize("mid,kind,digest", [
    ("../etc", "log", None), ("m4max/x", "log", None), ("", "log", None), (".hidden", "log", None),
    ("m4max", "secrets", None), ("m4max", "../log", None),
    ("m4max", "log", "A" * 64), ("m4max", "log", "0" * 63), ("m4max", "log", "0" * 64 + "\n"),
])
def test_store_object_refuses_bad_names(tmp_path, mid, kind, digest):
    body = b"x"
    with pytest.raises(ValueError):
        I.store_object(tmp_path, mid, kind, digest or sha(body), body)
    assert not (tmp_path / "objects").exists() or not any((tmp_path / "objects").rglob("*.obj"))


def test_store_object_sha_mismatch(tmp_path):
    with pytest.raises(ValueError):
        I.store_object(tmp_path, "m4max", "usage", sha(b"one"), b"two")
    assert not any(tmp_path.rglob("*.obj"))


def test_index_object_first_receipt_wins(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    assert I.index_object(db, "m4max", "log", "a" * 64, 10, NOW) is True
    assert I.index_object(db, "m4max", "log", "a" * 64, 10, NOW + 86400) is False
    assert I.index_object(db, "m5ultra", "log", "a" * 64, 10, NOW + 5) is True
    rows = db.execute("SELECT machine_id, kind, sha256, bytes, received_at, day FROM objects ORDER BY machine_id").fetchall()
    assert rows == [("m4max", "log", "a" * 64, 10, NOW, "2026-10-29"), ("m5ultra", "log", "a" * 64, 10, NOW + 5, "2026-10-29")]


def test_index_object_day_is_utc_and_committed(tmp_path):
    path = tmp_path / "i.sqlite"
    db = I.open_db(path)
    I.index_object(db, "m4max", "usage", "b" * 64, 3, 1793318399.9)    # 23:59:59.9Z
    I.index_object(db, "m4max", "usage", "c" * 64, 3, 1793318400.0)    # 00:00:00Z next day
    other = I.open_db(path)
    days = [r[0] for r in other.execute("SELECT day FROM objects ORDER BY sha256")]
    assert days == ["2026-10-29", "2026-10-30"], "visible to another connection (committed), UTC day boundary"
