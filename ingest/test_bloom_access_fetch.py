"""Frozen test: bloom_access.default_fetch (the opener is faked, no network)."""
import pytest

import bloom_access as A


class Resp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self.body if n < 0 else self.body[:n]


def test_default_fetch_returns_parsed_json_with_a_short_timeout(monkeypatch):
    seen = {}

    def fake(url, timeout=None):
        seen["url"], seen["timeout"] = url, timeout
        return Resp(b'{"keys": [{"kid": "k1"}]}')

    monkeypatch.setattr(A._OPENER, "open", fake)
    assert A.default_fetch("https://example-team.cloudflareaccess.com/cdn-cgi/access/certs") == {"keys": [{"kid": "k1"}]}
    assert seen == {"url": "https://example-team.cloudflareaccess.com/cdn-cgi/access/certs", "timeout": 5}


def test_default_fetch_lets_network_errors_and_bad_json_raise(monkeypatch):
    def boom(url, timeout=None):
        raise OSError("down")

    monkeypatch.setattr(A._OPENER, "open", boom)
    with pytest.raises(OSError):
        A.default_fetch("https://x.invalid/")
    monkeypatch.setattr(A._OPENER, "open", lambda url, timeout=None: Resp(b"not json"))
    with pytest.raises(ValueError):
        A.default_fetch("https://x.invalid/")


def test_failed_fetch_is_rate_limited_too():
    import bloom_access as A
    A.reset_cache()
    calls = []

    def bad(url):
        calls.append(url)
        raise OSError("down")
    for t in (1000, 1001, 1030):
        try:
            A._key_for("example-team.cloudflareaccess.com", "k", bad, t)
        except OSError:
            pass
    assert len(calls) == 1


def test_default_fetch_refuses_plain_http_and_redirects():
    import bloom_access as A
    try:
        A.default_fetch("http://example.invalid/x")
        assert False
    except ValueError:
        pass
    assert A._NoRedirect().redirect_request(None, None, 302, "", {}, "http://x") is None


def test_malformed_key_entry_is_skipped_not_fatal():
    import bloom_access as A
    A.reset_cache()
    doc = {"keys": [{"kty": "RSA", "kid": "bad"}, {"kty": "RSA", "kid": "ok", "n": "AQAB", "e": "AQAB"}]}
    assert A._key_for("example-team.cloudflareaccess.com", "ok", lambda u: doc, 5) is not None


def test_default_fetch_rejects_oversized_body(monkeypatch):
    monkeypatch.setattr(A._OPENER, "open", lambda url, timeout=None: Resp(b" " * (A.MAX_JWKS + 1)))
    with pytest.raises(ValueError):
        A.default_fetch("https://x.invalid/")
