"""Frozen test: bloom_ingest_ledger.manifest_run(root, db, day) writes hash-chained manifests and nothing else."""
import hashlib
import inspect
import json

import bloom_ingest as I
import bloom_ingest_ledger as IL
import bloom_ledger as L

DAY1 = 1793232000.0    # 2026-10-29T00:00:00Z
DAY2 = DAY1 + 86400


def add(root, db, mid, kind, body, at):
    digest = hashlib.sha256(body).hexdigest()
    I.store_object(root, mid, kind, digest, body)
    I.index_object(db, mid, kind, digest, len(body), at)
    return digest


def run_day(root, db, day):
    try:
        return IL.manifest_run(root, db, day)
    except TypeError as exc:
        raise AssertionError(f"manifest_run must accept (root, db, day): {exc}")


def setup(tmp_path):
    db = I.open_db(tmp_path / "index.sqlite")
    add(tmp_path, db, "m4max", "usage", b"u1", DAY1 + 10)
    add(tmp_path, db, "m4max", "log", b"l1", DAY1 + 20)
    c = add(tmp_path, db, "m4max", "log", b"l2", DAY2 + 5)
    add(tmp_path, db, "m5ultra", "log", b"x1", DAY1 + 30)
    return tmp_path, db, c


def test_signature_is_root_db_day_only():
    assert list(inspect.signature(IL.manifest_run).parameters) == ["root", "db", "day"]


def test_manifest_run_chains_and_verifies(tmp_path):
    root, db, c = setup(tmp_path)
    res = run_day(root, db, "2026-10-29")
    assert res == {"m4max": "written", "m5ultra": "written"}
    m1 = json.loads((root / "ledger" / "m4max" / "manifest-2026-10-29.json").read_text())
    assert m1["machine_id"] == "m4max" and m1["prev_hash"] == L.GENESIS
    assert [f["sha256"] for f in m1["files"]] == [f["sha256"] for f in IL.day_files(db, "m4max", "2026-10-29")]
    assert run_day(root, db, "2026-10-29") == {"m4max": "same", "m5ultra": "same"}
    assert run_day(root, db, "2026-10-30") == {"m4max": "written", "m5ultra": "written"}
    m2 = json.loads((root / "ledger" / "m4max" / "manifest-2026-10-30.json").read_text())
    assert m2["prev_hash"] == m1["chain_hash"]
    assert L.verify_chain(root, L.load_manifests(root / "ledger" / "m4max")) == []
    (root / "objects" / "m4max" / "log" / f"{c}.obj").write_bytes(b"tampered")
    assert L.verify_chain(root, L.load_manifests(root / "ledger" / "m4max")) != []


def test_manifest_run_skips_machine_not_yet_present_or_ahead(tmp_path):
    root, db, _ = setup(tmp_path)
    add(root, db, "newmac", "log", b"n1", DAY2 + 50)
    assert "newmac" not in run_day(root, db, "2026-10-29")
    run_day(root, db, "2026-10-30")
    assert run_day(root, db, "2026-10-28") == {}
    assert not (root / "ledger" / "m4max" / "manifest-2026-10-28.json").exists()


def test_manifest_run_writes_no_proof_files(tmp_path):
    root, db, _ = setup(tmp_path)
    run_day(root, db, "2026-10-29")
    names = sorted(p.name for p in (root / "ledger" / "m4max").iterdir())
    assert names == ["manifest-2026-10-29.json"], names
    src = inspect.getsource(IL).lower()
    for word in ("opentimestamps", "bitcoin", "ots_stamp", "subprocess"):
        assert word not in src, word
