"""Shared fixture for the settings route tests: a real ThreadingHTTPServer on a temp data dir (test support, not a test)."""
import hashlib
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

import bloom_ingest as I
import server as SV

ADMIN = "fixture-admin-token-0123456789abcdef"
NOW_BODY = b'{"m":1}\n'


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def web(tmp_path, monkeypatch):
    (tmp_path / "tokens").write_text(f"studio {sha('studio-token')}\n")
    monkeypatch.setattr(SV, "ROOT", tmp_path)
    monkeypatch.setattr(SV, "TOKENS_PATH", str(tmp_path / "tokens"))
    monkeypatch.setattr(SV, "MACHINES_PATH", str(tmp_path / "machines.json"), raising=False)
    monkeypatch.setattr(SV, "ADMIN_PATH", str(tmp_path / "bloom_admin"), raising=False)
    lines = []
    monkeypatch.setattr(SV, "log", lines.append)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), SV.Handler)
    srv.db = I.open_db(tmp_path / "index.sqlite")
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def call(method, path, body=None, token=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
        h = dict(headers or {})
        if token:
            h["Authorization"] = "Bearer " + token
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        out = (r.status, r.getheader("Content-Type"), r.read())
        c.close()
        return out

    call.admin_file = tmp_path / "bloom_admin"
    call.lines = lines
    yield call
    srv.shutdown()
    srv.server_close()


def post_object(call, token):
    return call("POST", "/v1/objects", NOW_BODY, token,
                {"X-Bloom-Kind": "log", "X-Bloom-Sha256": hashlib.sha256(NOW_BODY).hexdigest()})[0]
