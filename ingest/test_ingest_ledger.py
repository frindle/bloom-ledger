"""Test: bloom_ingest_ledger.day_files (manifest_run is covered by test_manifest_run_plain.py)."""
import hashlib

import bloom_ingest as I
import bloom_ingest_ledger as IL

DAY1 = 1793232000.0    # 2026-10-29T00:00:00Z
DAY2 = DAY1 + 86400


def add(root, db, mid, kind, body, at):
    digest = hashlib.sha256(body).hexdigest()
    I.store_object(root, mid, kind, digest, body)
    I.index_object(db, mid, kind, digest, len(body), at)
    return digest


def setup(tmp_path):
    root = tmp_path
    db = I.open_db(root / "index.sqlite")
    a = add(root, db, "mac-a", "usage", b"u1", DAY1 + 10)
    b = add(root, db, "mac-a", "log", b"l1", DAY1 + 20)
    c = add(root, db, "mac-a", "log", b"l2", DAY2 + 5)
    d = add(root, db, "mac-b", "log", b"x1", DAY1 + 30)
    return root, db, a, b, c, d


def test_day_files(tmp_path):
    root, db, a, b, c, d = setup(tmp_path)
    got = IL.day_files(db, "mac-a", "2026-10-29")
    assert got == sorted([{"path": f"objects/mac-a/usage/{a}.obj", "bytes": 2, "sha256": a},
                          {"path": f"objects/mac-a/log/{b}.obj", "bytes": 2, "sha256": b}], key=lambda f: f["path"])
    assert [f["sha256"] for f in IL.day_files(db, "mac-a", "2026-10-30")] == [c]
    assert IL.day_files(db, "mac-a", "2026-10-28") == []
    assert IL.day_files(db, "nobody", "2026-10-29") == []
