"""manifest_run skips a machine whose ledger already has a manifest for a later day, even when that machine has
objects on the requested day (test_manifest_run_plain only covers a day before every machine's first object).
Writing it anyway would put a manifest behind the chain head, and verify_chain would then report a break."""
import hashlib

import bloom_ingest as I
import bloom_ingest_ledger as IL
import bloom_ledger as L

DAY1 = 1793232000.0    # 2026-10-29T00:00:00Z
DAY2 = DAY1 + 86400


def add(root, db, mid, kind, body, at):
    digest = hashlib.sha256(body).hexdigest()
    I.store_object(root, mid, kind, digest, body)
    I.index_object(db, mid, kind, digest, len(body), at)


def test_day_behind_the_chain_head_is_skipped(tmp_path):
    db = I.open_db(tmp_path / "index.sqlite")
    add(tmp_path, db, "m4max", "log", b"l1", DAY1 + 20)
    add(tmp_path, db, "m4max", "log", b"l2", DAY2 + 5)
    assert IL.manifest_run(tmp_path, db, "2026-10-30") == {"m4max": "written"}
    ldir = tmp_path / "ledger" / "m4max"
    assert IL.manifest_run(tmp_path, db, "2026-10-29") == {}
    assert not (ldir / "manifest-2026-10-29.json").exists()
    assert L.verify_chain(tmp_path, L.load_manifests(ldir)) == []


def test_only_the_machine_that_is_ahead_is_skipped(tmp_path):
    db = I.open_db(tmp_path / "index.sqlite")
    add(tmp_path, db, "m4max", "log", b"l1", DAY1 + 20)
    add(tmp_path, db, "m4max", "log", b"l2", DAY2 + 5)
    assert IL.manifest_run(tmp_path, db, "2026-10-30") == {"m4max": "written"}
    add(tmp_path, db, "m5ultra", "log", b"x1", DAY1 + 30)   # a late shipper: its first object is on the earlier day
    assert IL.manifest_run(tmp_path, db, "2026-10-29") == {"m5ultra": "written"}
    assert not (tmp_path / "ledger" / "m4max" / "manifest-2026-10-29.json").exists()
    for mid in ("m4max", "m5ultra"):
        assert L.verify_chain(tmp_path, L.load_manifests(tmp_path / "ledger" / mid)) == [], mid
