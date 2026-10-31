"""Frozen test: bloom_lan.is_private_ip / forwarded_ok."""
import bloom_lan as L


def test_private_and_loopback_addresses():
    for ip in ("127.0.0.1", "10.0.12.50", "192.168.1.5", "172.16.0.9", "::1", "::ffff:10.1.2.3", " 10.0.0.1 "):
        assert L.is_private_ip(ip) is True, ip


def test_public_and_junk_addresses():
    for ip in ("8.8.8.8", "1.1.1.1", "2606:4700::1", "::ffff:8.8.8.8", "", "nope", None):
        assert L.is_private_ip(ip) is False, ip


def test_forwarded_headers():
    assert L.forwarded_ok({}) is True
    assert L.forwarded_ok({"X-Forwarded-For": "10.0.0.2, 192.168.1.9"}) is True
    assert L.forwarded_ok({"X-Forwarded-For": "10.0.0.2, 93.184.216.34"}) is False
    assert L.forwarded_ok({"X-Forwarded-For": "junk"}) is False
    assert L.forwarded_ok({"CF-Connecting-IP": "93.184.216.34"}) is False
