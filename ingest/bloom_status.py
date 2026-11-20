"""Data for the /status page and `doctor`: what is connected, when each Mac last sent data, and what to do about it."""
import shutil
import time

import bloom_alerts as AL
import bloom_integrations as IG
import bloom_settings as BS

HINTS = {
    "reporting": "Sending data normally.",
    "silent": "No data for over 30 minutes. Check the Mac is awake and online, then run the client doctor on it: "
              "python3 \"$HOME/Library/Application Support/bloom-ledger/client/bloom-doctor.py\"",
    "not-reporting-yet": "Added but nothing received yet. Run the install command on that Mac (Machines > New token shows it).",
    "removed": "Removed from the ledger. Old data is kept.",
}


def age_text(age_s):
    if age_s is None:
        return "never"
    if age_s < 90:
        return "just now"
    if age_s < 5400:
        return "%d min ago" % round(age_s / 60)
    if age_s < 172800:
        return "%d h ago" % round(age_s / 3600)
    return "%d days ago" % round(age_s / 86400)


def build(db, root, now, machine_ids, version, auth_mode, timezone, export_api):
    rows = BS.machine_rows(db, root, now, machine_ids)
    macs = []
    for r in rows:
        last = r.get("last_seen")
        age = None if last is None else max(0, int(now - last))
        name = (r.get("profile") or {}).get("display_name") or r["id"]
        macs.append({"id": r["id"], "name": name, "status": r["status"], "last_seen": last, "age_s": age, "age_text": age_text(age),
                     "objects": r.get("objects", 0), "days_sealed": r.get("days_sealed", 0), "hint": HINTS.get(r["status"], "")})
    try:
        free = shutil.disk_usage(str(root)).free
    except OSError:
        free = None
    return {"generated_at": int(now), "version": version, "auth_mode": auth_mode, "timezone": timezone, "export_api": bool(export_api),
            "machines": macs, "alerts": AL.evaluate_alerts(db, now), "disk_free_bytes": free,
            "integrations": IG.describe(db), "overall": overall(macs)}


def overall(macs):
    if not macs:
        return {"state": "empty", "text": "No Macs added yet."}
    live = [m for m in macs if m["status"] == "reporting"]
    if len(live) == len([m for m in macs if m["status"] != "removed"]) and live:
        return {"state": "ok", "text": "All %d Mac%s reporting." % (len(live), "" if len(live) == 1 else "s")}
    if live:
        return {"state": "warn", "text": "%d of %d Macs reporting." % (len(live), len([m for m in macs if m["status"] != "removed"]))}
    return {"state": "bad", "text": "No Mac is reporting right now."}
