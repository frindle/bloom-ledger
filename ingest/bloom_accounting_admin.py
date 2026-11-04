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
        if key == "write_off":
            import bloom_accounting_writeoff as WO
            errs = WO.validate(data.get("value"))
            if errs:
                return (400, {"error": "; ".join(errs)})
        if key == "machines" and data.get("value") is not None:
            errs = machines_errors(data.get("value"))
            if errs:
                return (400, {"error": "; ".join(errs)})
        AC.set_setting(db, key, data.get("value"), effective_from, int(now))
        return (200, {"ok": True})
    return (404, {"error": "not found"})


def machines_errors(value):
    """[] when `value` is a usable list of machine records, else plain-language problems (one per bad field)."""
    import bloom_accounting_machines as M
    if not isinstance(value, list):
        return ["machines must be a list"]
    errs, seen = [], set()
    for i, m in enumerate(value):
        name = m.get("id") if isinstance(m, dict) and isinstance(m.get("id"), str) else "#%d" % (i + 1)
        errs += ["%s: %s" % (name, msg) for msg in M.validate_machine(m).values()]
        if name in seen:
            errs.append("%s: listed twice" % name)
        seen.add(name)
    return errs
