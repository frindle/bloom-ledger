"""Where the Mac client may send its token: plain http only to private/loopback IPs, localhost and .local; never follow redirects."""
import importlib.util
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

CLIENT = Path(__file__).resolve().parents[1] / "client"
sys.path.insert(0, str(CLIENT))
import bloom_ship as S  # noqa: E402


@pytest.mark.parametrize("url,ok", [
    ("http://192.168.1.20:8787", True), ("http://10.0.0.5:8787", True), ("http://100.64.3.4:8787", True),
    ("http://127.0.0.1:8787", True), ("http://localhost:8787", True), ("http://[::1]:8787", True),
    ("http://mac-mini.local:8787", True), ("http://MAC.LOCAL", True),
    ("https://ledger.example.com", True), ("https://tower", True),
    ("http://ledger.example.com", False), ("http://tower:8787", False), ("http://evil.local.example.com", False),
    ("http://8.8.8.8:8787", False), ("https://8.8.8.8", False), ("ftp://192.168.1.2", False), ("", False), ("http://", False),
])
def test_is_lan_url(url, ok):
    assert S.is_lan_url(url) is ok


def _two_servers():
    seen = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    tgt = HTTPServer(("127.0.0.1", 0), Target)

    class Redirector(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:%d/" % tgt.server_address[1])
            self.end_headers()

        def log_message(self, *a):
            pass

    red = HTTPServer(("127.0.0.1", 0), Redirector)
    for s in (tgt, red):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    return red, tgt, seen


def test_doctor_does_not_follow_redirects_with_the_token():
    spec = importlib.util.spec_from_file_location("bloom_doctor_cli", CLIENT / "bloom-doctor.py")
    doctor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(doctor)
    red, tgt, seen = _two_servers()
    try:
        status, _body = doctor.get("http://127.0.0.1:%d/" % red.server_address[1], token="secret-token")
        assert status == 302
        assert seen == []          # the second server never saw a request, let alone the Authorization header
    finally:
        red.shutdown(); tgt.shutdown(); red.server_close(); tgt.server_close()


def test_shipper_opener_does_not_follow_redirects():
    import urllib.error
    import urllib.request
    red, tgt, seen = _two_servers()
    try:
        req = urllib.request.Request("http://127.0.0.1:%d/" % red.server_address[1], headers={"Authorization": "Bearer secret-token"})
        with pytest.raises(urllib.error.HTTPError) as e:
            S.open_no_redirect(req, timeout=5)
        assert e.value.code == 302 and seen == []
    finally:
        red.shutdown(); tgt.shutdown(); red.server_close(); tgt.server_close()
