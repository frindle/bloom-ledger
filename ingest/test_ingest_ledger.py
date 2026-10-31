"""Frozen test: bloom_ingest_ledger.day_files and bloom_ingest_ledger.manifest_run. No real ots binary."""
import hashlib
import json
import subprocess
from pathlib import Path

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


def fake_ots(calls, rc=0):
    def run(argv, **kw):
        calls.append(argv)
        if argv[1] == "stamp" and rc == 0:
            Path(argv[2] + ".ots").write_bytes(b"proof")
        return subprocess.CompletedProcess(argv, rc, "", "")
    return run


def setup(tmp_path):
    root = tmp_path
    db = I.open_db(root / "index.sqlite")
    a = add(root, db, "m4max", "usage", b"u1", DAY1 + 10)
    b = add(root, db, "m4max", "log", b"l1", DAY1 + 20)
    c = add(root, db, "m4max", "log", b"l2", DAY2 + 5)
    d = add(root, db, "m5ultra", "log", b"x1", DAY1 + 30)
    return root, db, a, b, c, d


def test_day_files(tmp_path):
    root, db, a, b, c, d = setup(tmp_path)
    got = IL.day_files(db, "m4max", "2026-10-29")
    assert got == sorted([{"path": f"objects/m4max/usage/{a}.obj", "bytes": 2, "sha256": a},
                          {"path": f"objects/m4max/log/{b}.obj", "bytes": 2, "sha256": b}], key=lambda f: f["path"])
    assert [f["sha256"] for f in IL.day_files(db, "m4max", "2026-10-30")] == [c]
    assert IL.day_files(db, "m4max", "2026-10-28") == []
    assert IL.day_files(db, "nobody", "2026-10-29") == []


def test_manifest_run_chains_stamps_and_verifies(tmp_path):
    root, db, a, b, c, d = setup(tmp_path)
    calls = []
    res = IL.manifest_run(root, db, "2026-10-29", "/fake/ots", DAY2 + 600, run=fake_ots(calls))
    assert res == {"m4max": "written", "m5ultra": "written"}
    m1 = json.loads((root / "ledger" / "m4max" / "manifest-2026-10-29.json").read_text())
    assert m1["machine_id"] == "m4max" and m1["prev_hash"] == L.GENESIS
    assert [f["sha256"] for f in m1["files"]] == [f["sha256"] for f in IL.day_files(db, "m4max", "2026-10-29")]
    assert len(calls) == 2 and all(x[1] == "stamp" for x in calls)
    ots = db.execute("SELECT machine_id, manifest, stamped_at, upgraded_at FROM ots ORDER BY machine_id").fetchall()
    assert ots == [("m4max", "manifest-2026-10-29.json", DAY2 + 600, None),
                   ("m5ultra", "manifest-2026-10-29.json", DAY2 + 600, None)]
    again = IL.manifest_run(root, db, "2026-10-29", "/fake/ots", DAY2 + 1200, run=fake_ots(calls))
    assert again == {"m4max": "same", "m5ultra": "same"} and len(calls) == 2, "a re-run neither rewrites nor restamps"
    res2 = IL.manifest_run(root, db, "2026-10-30", "/fake/ots", DAY2 + 86400, run=fake_ots(calls))
    assert res2 == {"m4max": "written", "m5ultra": "written"}
    m2 = json.loads((root / "ledger" / "m4max" / "manifest-2026-10-30.json").read_text())
    assert m2["prev_hash"] == m1["chain_hash"]
    assert L.verify_chain(root, L.load_manifests(root / "ledger" / "m4max")) == []
    (root / "objects" / "m4max" / "log" / f"{c}.obj").write_bytes(b"tampered")
    assert L.verify_chain(root, L.load_manifests(root / "ledger" / "m4max")) != []


def test_manifest_run_skips_machine_not_yet_present_or_ahead(tmp_path):
    root, db, *_ = setup(tmp_path)
    add(root, db, "newmac", "log", b"n1", DAY2 + 50)
    res = IL.manifest_run(root, db, "2026-10-29", None, DAY2, run=fake_ots([]))
    assert "newmac" not in res, "no manifest for a day before the machine's first object"
    IL.manifest_run(root, db, "2026-10-30", None, DAY2 + 86400, run=fake_ots([]))
    res = IL.manifest_run(root, db, "2026-10-28", None, DAY2 + 86400, run=fake_ots([]))
    assert res == {}, "a machine whose chain is already past `day` is not rewritten (and m4max had nothing then)"
    assert not (root / "ledger" / "m4max" / "manifest-2026-10-28.json").exists()


def test_manifest_run_without_ots_records_nothing(tmp_path):
    root, db, *_ = setup(tmp_path)
    calls = []
    res = IL.manifest_run(root, db, "2026-10-29", None, DAY2, run=fake_ots(calls))
    assert set(res.values()) == {"written"} and calls == []
    assert db.execute("SELECT COUNT(*) FROM ots").fetchone()[0] == 0, "skipped stamps are not tracked as stamped"
    failed = []
    root2 = tmp_path / "second"
    root2.mkdir()
    db2 = I.open_db(root2 / "index.sqlite")
    add(root2, db2, "m4max", "log", b"z", DAY1)
    IL.manifest_run(root2, db2, "2026-10-29", "/fake/ots", DAY2, run=fake_ots(failed, rc=1))
    assert db2.execute("SELECT COUNT(*) FROM ots").fetchone()[0] == 0, "a failed stamp is not tracked as stamped"
