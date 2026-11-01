"""Accounting admin API: authenticated writes for entries and settings, open reads.

Writes need the admin token (same check as the settings page). Not tax advice."""
import json

import bloom_accounting_entries as AE
import bloom_accounting_config as AC
import bloom_settings as BS


def accounting_post(path, headers, body, db, now):
    """Handle POST /v1/accounting/*; returns (status, json-able object)."""
    try:
        data = json.loads(body)
    except ValueError:
        return (400, {"error": "bad request"})
    if not isinstance(data, dict):
        return (400, {"error": "bad request"})
    if path == "/v1/accounting/entries":
        err = AE.validate_entry(data)
        if err:
            return (400, {"error": err})
        return (201, {"id": AE.add_entry(db, data, int(now))})
    if path == "/v1/accounting/entries/void":
        eid = data.get("id")
        if not isinstance(eid, int) or isinstance(eid, bool):
            return (400, {"error": "bad id"})
        if not AE.void_entry(db, eid, int(now)):
            return (404, {"error": "not found"})
        return (200, {"ok": True})
    if path == "/v1/accounting/settings":
        key = data.get("key")
        if key not in AC.DEFAULTS:
            return (400, {"error": "bad key"})
        effective_from = data.get("effective_from")
        if not isinstance(effective_from, str) or len(effective_from) != 10:
            return (400, {"error": "bad effective_from"})
        AC.set_setting(db, key, data.get("value"), effective_from, int(now))
        return (200, {"ok": True})
    return (404, {"error": "not found"})
