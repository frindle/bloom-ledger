"""Accounting index for the bloom-ledger ingest (stdlib only): derived, rebuildable sqlite tables parsed from the
write-once log objects. Money is integer micro-USD or cents. Bookkeeping estimates, not tax advice."""

TABLES = ("power_minutes", "earnings", "account_totals", "acct_cursor", "acct_parse_errors")


def create_schema(db):
    """Create every table in TABLES if missing (idempotent)."""
    raise NotImplementedError("create_schema")


def route(path):
    """Map an object's meta path to 'power', 'earnings', 'totals' or None."""
    raise NotImplementedError("route")


def is_parsed(db, machine_id, sha):
    """True when mark_parsed was called for this (machine_id, sha)."""
    raise NotImplementedError("is_parsed")


def mark_parsed(db, machine_id, sha):
    """Record (machine_id, sha) as parsed; calling twice is harmless."""
    raise NotImplementedError("mark_parsed")


def reset(db):
    """Drop and recreate the derived tables in TABLES; never touch any other table."""
    raise NotImplementedError("reset")
