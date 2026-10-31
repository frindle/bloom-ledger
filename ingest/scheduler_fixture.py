"""Test support (not a test): run server.scheduler for one tick against a temp data dir with one stored earnings object."""
import hashlib
import json

import pytest

import bloom_accounting_index as A
import bloom_ingest as I
import server as S

NOW = 1793300000.0


class OneTick:
    def __init__(self):
        self.calls = 0

    def wait(self, timeout=None):
        self.calls += 1
        return self.calls > 2


@pytest.fixture
def tick(tmp_path, monkeypatch):
    root = tmp_path / "data"
    db = I.open_db(tmp_path / "i.sqlite")
    er = json.dumps({"_id": "L1", "created_at": "2026-10-20T12:00:00Z", "amount_micro_usd": 700, "job_id": "j"}) + "\n"
    body = json.dumps({"path": "earnings-archive/earnings-2026-10.jsonl", "offset": 0, "bytes": len(er)}).encode() + b"\n" + er.encode()
    sha = hashlib.sha256(body).hexdigest()
    I.store_object(root, "m1", "log", sha, body)
    I.index_object(db, "m1", "log", sha, len(body), NOW)
    logs = []
    monkeypatch.setattr(S, "ROOT", root)
    monkeypatch.setattr(S, "log", logs.append)

    def run(fail=False):
        if fail:
            def boom(db_, root_):
                raise RuntimeError("boom")
            monkeypatch.setattr(A, "index_new", boom)
        S.scheduler(db, OneTick())
        return db, logs
    return run
