"""Alerts for the bloom-ledger ingest (stdlib only): a Mac went silent, a Mac stopped snapshotting the usage ring
(it rolls off after ~40 h), or an OpenTimestamps proof was never upgraded to a Bitcoin attestation."""

SILENT_S = 30 * 60
RING_S = 12 * 3600
OTS_S = 48 * 3600


def evaluate_alerts(db, now, silent_s=SILENT_S, ring_s=RING_S, ots_s=OTS_S):
    """[{'alert', 'machine_id', 'age_s', ...}] of every open alert, in a stable order."""
    alerts = []
    for mid, last in db.execute(
        "SELECT machine_id, MAX(received_at) FROM objects GROUP BY machine_id ORDER BY machine_id"
    ):
        age = now - last
        if age > silent_s:
            alerts.append({"alert": "machine-silent", "machine_id": mid, "age_s": int(age)})
        ring = db.execute(
            "SELECT MAX(received_at) FROM objects WHERE machine_id = ? AND kind = 'archive-run'",
            (mid,)
        ).fetchone()
        ring_val = ring[0] if ring else None
        if ring_val is None:
            alerts.append({"alert": "ring-snapshot-stale", "machine_id": mid, "age_s": None})
        elif (now - ring_val) > ring_s:
            alerts.append({"alert": "ring-snapshot-stale", "machine_id": mid, "age_s": int(now - ring_val)})
    for mid, manifest, stamped in db.execute(
        "SELECT machine_id, manifest, stamped_at FROM ots WHERE upgraded_at IS NULL ORDER BY machine_id, manifest"
    ):
        age = now - stamped
        if age > ots_s:
            alerts.append({"alert": "ots-not-upgraded", "machine_id": mid, "manifest": manifest, "age_s": int(age)})
    return alerts


def record_upgrades(db, machine_id, results, now):
    """Mark manifests whose `ots upgrade` succeeded. results: {manifest file name: status}. Returns rows updated."""
    total = 0
    for name, st in sorted((results or {}).items()):
        if st != "upgraded":
            continue
        cur = db.execute(
            "UPDATE ots SET upgraded_at = ? WHERE machine_id = ? AND manifest = ? AND upgraded_at IS NULL",
            (float(now), machine_id, name)
        )
        total += cur.rowcount
    db.commit()
    return total


def alert_key(a):
    return f"{a['alert']}:{a['machine_id']}:{a.get('manifest', '')}"
