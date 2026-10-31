"""LAN-only write guard for the ledger: private client address, no public proxy hop, same-origin browser writes.

The ledger is a local service; this replaces the admin key for settings writes."""
from urllib.parse import urlparse
import ipaddress


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


def write_guard(client_ip, headers):
    if not is_private_ip(client_ip) or not forwarded_ok(headers):
        return (403, {"error": "local network only"})
    if not same_origin(headers):
        return (403, {"error": "cross-origin write blocked"})
    return None
