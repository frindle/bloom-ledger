"""Dashboard summary for the bloom-ledger ingest (stdlib only). Metadata only: counts, sizes, days, manifest chain
hashes and OpenTimestamps state; never an object's contents."""
import datetime as dt

import bloom_ingest_ledger as IL
import bloom_ledger as L

WINDOW_DAYS = 90


def summary(db, root, now):
    """{'generated_at', 'machines': [{'id', 'first_day', 'last_seen', 'objects', 'days'}]}; days is the contiguous
    ascending run of UTC days from max(first_day, today - 89) to today."""
    today = dt.datetime.fromtimestamp(now, dt.timezone.utc).date()
    floor = today - dt.timedelta(days=WINDOW_DAYS - 1)
    out = []
    for mid in IL.machines(db):
        first, last = db.execute("SELECT MIN(day), MAX(received_at) FROM objects WHERE machine_id = ?",
                                 (mid,)).fetchone()
        kinds = dict(db.execute("SELECT kind, COUNT(*) FROM objects WHERE machine_id = ? GROUP BY kind", (mid,)))
        per_day = {d: (n, b or 0) for d, n, b in db.execute(
            "SELECT day, COUNT(*), SUM(bytes) FROM objects WHERE machine_id = ? GROUP BY day", (mid,))}
        manifests = dict(L.load_manifests(IL.ledger_dir(root, mid)))
        ots = {name: (stamped, up) for name, stamped, up in db.execute(
            "SELECT manifest, stamped_at, upgraded_at FROM ots WHERE machine_id = ?", (mid,))}
        d = max(dt.date.fromisoformat(first), floor)
        days = []
        while d <= today:
            ds = d.isoformat()
            files, nbytes = per_day.get(ds, (0, 0))
            if ds in manifests:
                state = "sealed"
            elif d == today:
                state = "open"
            else:
                state = "missing"
            stamped, up = ots.get(f"manifest-{ds}.json", (None, None))
            days.append({"day": ds, "files": files, "bytes": nbytes, "state": state,
                         "chain_hash": (manifests.get(ds) or {}).get("chain_hash"),
                         "ots": "bitcoin" if up is not None else "stamped" if stamped is not None else "none"})
            d += dt.timedelta(days=1)
        out.append({"id": mid, "first_day": first, "last_seen": int(last), "objects": kinds, "days": days})
    return {"generated_at": int(now), "machines": out}
