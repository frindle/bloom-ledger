"""Scoped API keys for another app on the local network (stdlib only).

A key is created by the logged-in owner on the Settings page, shown once, and stored only as a sha256 hash.
It is sent as `Authorization: Bearer blk_...` and authorizes a short list of routes (see in_scope) and nothing else.
It is separate from the per-machine upload tokens (POST /v1/objects), which have no `blk_` prefix and their own checks."""
import hashlib
import hmac
import secrets
import time

import bloom_accounting_receipts as RC

PREFIX = "blk_"
MAX_LABEL = 60
MAX_KEYS = 20


def create_table(db):
    db.execute("CREATE TABLE IF NOT EXISTS bl_api_keys (id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL,"
               " key_hash TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL, last_used_at INTEGER, revoked_at INTEGER)")
    db.commit()


def _hash(key):
    return hashlib.sha256(key.encode()).hexdigest()


def create(db, label, now=None):
    """Make a key. Returns (id, full key); the full key is never stored. ValueError (plain message) for a bad label."""
    label = (label or "").strip() if isinstance(label, str) else ""
    if not 1 <= len(label) <= MAX_LABEL or not label.isprintable():
        raise ValueError("Give the key a label (1 to %d characters)." % MAX_LABEL)
    create_table(db)
    if db.execute("SELECT COUNT(*) FROM bl_api_keys WHERE revoked_at IS NULL").fetchone()[0] >= MAX_KEYS:
        raise ValueError("Too many active keys. Revoke one first.")
    key = PREFIX + secrets.token_urlsafe(32)
    cur = db.execute("INSERT INTO bl_api_keys (label, key_hash, created_at) VALUES (?, ?, ?)",
                     (label, _hash(key), int(now or time.time())))
    db.commit()
    return cur.lastrowid, key


def list_keys(db):
    """Label, created and last used for each key that is not revoked (never the key or its hash)."""
    create_table(db)
    return [{"id": r[0], "label": r[1], "created_at": r[2], "last_used_at": r[3]}
            for r in db.execute("SELECT id, label, created_at, last_used_at FROM bl_api_keys"
                                " WHERE revoked_at IS NULL ORDER BY id").fetchall()]


def revoke(db, key_id, now=None):
    """True when an active key was revoked."""
    create_table(db)
    cur = db.execute("UPDATE bl_api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                     (int(now or time.time()), key_id))
    db.commit()
    return cur.rowcount == 1


def revoke_label(db, label, keep_id=None, now=None):
    """Revoke every active key with this label (except `keep_id`). Returns how many were revoked."""
    create_table(db)
    cur = db.execute("UPDATE bl_api_keys SET revoked_at = ? WHERE label = ? AND revoked_at IS NULL AND id IS NOT ?",
                     (int(now or time.time()), label, keep_id))
    db.commit()
    return cur.rowcount


def bearer_key(headers):
    """The `blk_...` key in an Authorization header, else None (machine tokens and other schemes are not ours)."""
    auth = (headers.get("Authorization") or "").strip()
    if auth[:7].lower() == "bearer " and auth[7:].strip().startswith(PREFIX):
        return auth[7:].strip()
    return None


def verify(db, key, now=None):
    """The key's id when it is known and not revoked (constant-time compare; last-used is updated), else None."""
    create_table(db)
    want = _hash(key).encode()
    found = None
    for kid, h in db.execute("SELECT id, key_hash FROM bl_api_keys WHERE revoked_at IS NULL").fetchall():
        if hmac.compare_digest(h.encode(), want):
            found = kid
    if found is not None:
        db.execute("UPDATE bl_api_keys SET last_used_at = ? WHERE id = ?", (int(now or time.time()), found))
        db.commit()
    return found


def in_scope(method, path):
    """The only requests a key may make: add, void and receipt on accounting entries, and the machine list."""
    path = path.split("?", 1)[0]
    if method == "POST":
        return path in ("/v1/accounting/entries", "/v1/accounting/entries/void") or RC.entry_id_from_path(path) is not None
    if method == "GET":
        return path == "/v1/settings"
    return False
