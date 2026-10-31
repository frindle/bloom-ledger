"""LAN-only write guard for the ledger: private client address, no public proxy hop, same-origin browser writes.

The ledger is a local service; this replaces the admin key for settings writes."""
import ipaddress


def is_private_ip(ip):
    try:
        addr = ipaddress.ip_address(str(ip).strip())
    except (ValueError, TypeError):
        return False
    if hasattr(addr, 'ipv4_mapped') and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr.is_loopback or addr.is_private


def forwarded_ok(headers):
    if headers.get("CF-Connecting-IP"):
        return False
    xff = headers.get("X-Forwarded-For")
    if not xff:
        return True
    return all(is_private_ip(hop) for hop in xff.split(','))
