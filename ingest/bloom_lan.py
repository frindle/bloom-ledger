"""LAN-only write guard for the ledger: private client address, no public proxy hop, same-origin browser writes.

The ledger is a local service; this replaces the admin key for settings writes."""
from urllib.parse import urlparse
import ipaddress
import os
import re
import time
import bloom_access


def is_private_ip(ip):
    """True for loopback or private-range addresses (IPv4-mapped IPv6 included); False for anything else or junk."""
    try:
        a = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return False
    a = getattr(a, "ipv4_mapped", None) or a
    return a.is_loopback or a.is_private


def forwarded_ok(headers):
    """False when CF-Connecting-IP is present or any X-Forwarded-For hop is not a private address."""
    if headers.get("CF-Connecting-IP"):
        return False
    xff = headers.get("X-Forwarded-For")
    if not xff:
        return True
    return all(is_private_ip(h) for h in xff.split(","))


def same_origin(headers):
    origin = headers.get("Origin")
    host = headers.get("Host")
    if not origin or not host:
        return False
    return urlparse(origin).netloc.lower() == host.strip().lower()


def access_ok(headers, env, fetch_jwks, now):
    team = (env.get("BLOOM_ACCESS_TEAM_DOMAIN") or "").strip()
    aud = (env.get("BLOOM_ACCESS_AUD") or "").strip()
    if not aud or not re.fullmatch(r"[a-z0-9-]+\.cloudflareaccess\.com", team):
        return False
    token = headers.get("Cf-Access-Jwt-Assertion")
    return bloom_access.verify(token, team, aud, fetch_jwks or bloom_access.default_fetch, now) is not None


def write_guard(client_ip, headers, env=None, fetch_jwks=None, now=None):
    env = os.environ if env is None else env
    now = time.time() if now is None else now
    if not is_private_ip(client_ip) or not forwarded_ok(headers):
        if not access_ok(headers, env, fetch_jwks, now):
            return (403, {"error": "local network only"})
    if not same_origin(headers):
        return (403, {"error": "cross-origin write blocked"})
    return None
