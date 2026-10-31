"""LAN-only write guard for the ledger: private client address, no public proxy hop, same-origin browser writes.

The ledger is a local service; this replaces the admin key for settings writes."""
import ipaddress


def is_private_ip(ip):
    raise NotImplementedError("is_private_ip")


def forwarded_ok(headers):
    raise NotImplementedError("forwarded_ok")
