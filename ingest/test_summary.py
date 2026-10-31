"""Frozen test: bloom_summary.summary and GET / (dashboard) / GET /v1/summary."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import bloom_ingest as I
import bloom_ledger as L
import bloom_summary as S

NOW = 1793300000.0  # 2026-10-29 UTC
TODAY = I.utc_day(NOW)


def seed(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    day = lambda n: I.utc_day(NOW - n * 86400)
    I.index_object(db, "m4max", "log", "a" * 64, 10, NOW - 3 * 86400)
    I.index_object(db, "m4max", "usage", "b" * 64, 5, NOW - 3 * 86400)
    I.index_object(db, "m4max", "log", "c" * 64, 7, NOW - 60)
    ldir = tmp_path / "ledger" / "m4max"
    man = L.make_manifest(day(3), "m4max", [], None)
    L.write_manifest(ldir, man)
    db.execute("INSERT INTO ots (machine_id, manifest, stamped_at) VALUES ('m4max', ?, ?)",
               (f"manifest-{day(3)}.json", NOW - 100))
    db.commit()
    return db, man


def test_shape(tmp_path):
    db, man = seed(tmp_path)
    got = S.summary(db, tmp_path, NOW)
    assert got["generated_at"] == int(NOW)
    (m,) = got["machines"]
    assert m["id"] == "m4max" and m["first_day"] == I.utc_day(NOW - 3 * 86400)
    assert m["last_seen"] == int(NOW - 60) and m["objects"] == {"log": 2, "usage": 1}
    assert [d["day"] for d in m["days"]][-1] == TODAY and len(m["days"]) == 4
    assert set(m["days"][0]) == {"day", "files", "bytes", "state", "chain_hash", "ots"}
    assert m["days"][0]["files"] == 2 and m["days"][0]["bytes"] == 15
    assert m["days"][0]["chain_hash"] == man["chain_hash"]


def test_states(tmp_path):
    db, _ = seed(tmp_path)
    days = S.summary(db, tmp_path, NOW)["machines"][0]["days"]
    assert [d["state"] for d in days] == ["sealed", "missing", "missing", "open"]
    assert days[1]["files"] == 0 and days[1]["chain_hash"] is None


def test_ots_states(tmp_path):
    db, _ = seed(tmp_path)
    d0 = I.utc_day(NOW - 3 * 86400)
    key = lambda: S.summary(db, tmp_path, NOW)["machines"][0]["days"][0]["ots"]
    assert key() == "stamped"
    db.execute("UPDATE ots SET upgraded_at = ?", (NOW,))
    assert key() == "bitcoin"
    db.execute("DELETE FROM ots")
    assert key() == "none" and d0


def test_window_capped_at_90(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    I.index_object(db, "m4max", "log", "a" * 64, 1, NOW - 200 * 86400)
    days = S.summary(db, tmp_path, NOW)["machines"][0]["days"]
    assert len(days) == 90 and days[-1]["day"] == TODAY


def test_root_serves_dashboard(tmp_path, monkeypatch):
    import server
    db, _ = seed(tmp_path)
    monkeypatch.setattr(server, "ROOT", tmp_path)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    srv.db = db
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = urllib.request.urlopen(f"http://127.0.0.1:{srv.server_port}/")
        assert r.status == 200 and r.headers["Content-Type"].startswith("text/html")
        assert b"/v1/summary" in r.read()
        r = urllib.request.urlopen(f"http://127.0.0.1:{srv.server_port}/v1/summary")
        assert json.loads(r.read())["machines"][0]["id"] == "m4max"
    finally:
        srv.shutdown()
