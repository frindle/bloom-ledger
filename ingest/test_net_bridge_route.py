"""Frozen test (step 3): index_new routes the net-bytes sidecar and joins it to power minutes in either order."""
import hashlib
import json

import bloom_accounting_index as A
import bloom_ingest as I

NOW = 1793800000.0
PW = ",".join(A.LEGACY_POWER_COLUMNS) + "\n2026-11-03T08:03:02Z,60,60,1,150,200,2.5,1,serving,0.5,1,10,m,0,50,0,,\n"
SIDE = ("ts_utc,gpu_bytes_in,gpu_bytes_out,sandbox_bytes_in,sandbox_bytes_out,total_bytes_in,total_bytes_out\n"
        "2026-11-03T08:03:02Z,9944,43121,131362,6498012,5394618,8260981\n")


def put(db, root, path, payload):
    body = json.dumps({"path": path, "offset": 0, "bytes": len(payload)}, sort_keys=True).encode() + b"\n" + payload.encode()
    sha = hashlib.sha256(body).hexdigest()
    I.store_object(root, "m1", "log", sha, body)
    I.index_object(db, "m1", "log", sha, len(body), NOW)


def bytes_in(db):
    row = db.execute("SELECT gpu_bytes_in, total_bytes_out FROM power_minutes").fetchone()
    assert row is not None, "power minute was not stored"
    return list(row)


def test_route():
    assert A.route("power/net-bytes-2026-11.csv") == "net"
    assert A.route("power/net-bytes-2026-11.csv.bak") is None


def test_index_new_joins_in_either_order(tmp_path):
    for order in ((("power/net-bytes-2026-11.csv", SIDE), ("power/power-log-2026-11.csv", PW)),
                  (("power/power-log-2026-11.csv", PW), ("power/net-bytes-2026-11.csv", SIDE))):
        d = tmp_path / order[0][0].split("/")[1].split("-")[0]
        d.mkdir()
        root = d / "data"
        db = I.open_db(d / "i.sqlite")
        A.create_schema(db)
        for path, payload in order:
            put(db, root, path, payload)
        assert A.index_new(db, root) == 2
        assert bytes_in(db) == [9944, 8260981], order[0][0]
