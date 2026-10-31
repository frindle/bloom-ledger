"""Frozen test: bloom_lan.same_origin / write_guard."""
import bloom_lan as L

OK = {"Origin": "http://10.0.0.5:8080", "Host": "10.0.0.5:8080"}


def test_same_origin_rules():
    assert L.same_origin(OK) is True
    assert L.same_origin({"Origin": "HTTP://Ledger.Lan", "Host": "ledger.lan"}) is True
    assert L.same_origin({"Origin": "http://evil.example", "Host": "10.0.0.5:8080"}) is False
    assert L.same_origin({"Host": "10.0.0.5:8080"}) is False
    assert L.same_origin({"Origin": "http://10.0.0.5:8080"}) is False


def test_write_guard_allows_local_same_origin():
    assert L.write_guard("10.0.0.7", OK) is None
    assert L.write_guard("127.0.0.1", OK) is None


def test_write_guard_rejections_and_order():
    assert L.write_guard("8.8.8.8", OK) == (403, {"error": "local network only"})
    assert L.write_guard("10.0.0.7", dict(OK, **{"CF-Connecting-IP": "8.8.8.8"})) == (403, {"error": "local network only"})
    assert L.write_guard("10.0.0.7", dict(OK, **{"X-Forwarded-For": "8.8.8.8"})) == (403, {"error": "local network only"})
    assert L.write_guard("10.0.0.7", {"Origin": "http://evil.example", "Host": "10.0.0.5"}) == (403, {"error": "cross-origin write blocked"})
    assert L.write_guard("8.8.8.8", {"Origin": "http://evil.example", "Host": "x"}) == (403, {"error": "local network only"})
