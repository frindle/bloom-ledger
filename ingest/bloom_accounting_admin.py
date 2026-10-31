"""Accounting admin API: authenticated writes for entries and settings, open reads.

Writes need the admin token (same check as the settings page). Not tax advice."""
import json

import bloom_accounting_entries as AE
import bloom_settings as BS


def accounting_post(path, headers, body, admin_path, db, now):
    denied = BS.admin_check(headers, admin_path)
    if denied is not None:
        return denied
    try:
        data = json.loads(body)
    except Exception:
        return (400, {"error": "bad request"})
    if not isinstance(data, dict):
        return (400, {"error": "bad request"})
    if path == "/v1/accounting/entries":
        err = AE.validate_entry(data)
        if err is not None:
            return (400, {"error": err})
        return (201, {"id": AE.add_entry(db, data, int(now))})
    return (404, {"error": "not found"})
