"""Admin login for the web UI (stdlib only): one admin account, salted PBKDF2 password, server-side sessions.

Modes (auth_mode):
  off    BLOOM_AUTH=off: no login, the old rule applies (private network address plus same-origin).
  login  an admin exists: anything that writes needs a valid session cookie (or Cloudflare Access) and same-origin.
  setup  fresh install, no admin yet: writes are refused until /setup creates one.
  lan    an older install with no admin yet: the old private-network rule still applies until /setup is used.
Passwords are never stored or logged; sessions are stored as sha256 of the cookie value."""
import hashlib
import hmac
import os
import secrets
import time

ITERATIONS = 200_000
SESSION_S = 30 * 86400
COOKIE = "bl_session"
MIN_PASSWORD = 8
MAX_FAILS = 5
LOCK_S = 60
_fails = {}


def create_tables(db):
    db.execute("CREATE TABLE IF NOT EXISTS bl_admin (id INTEGER PRIMARY KEY CHECK (id = 1), username TEXT NOT NULL, salt TEXT NOT NULL,"
               " pw_hash TEXT NOT NULL, iters INTEGER NOT NULL, created_at INTEGER NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS bl_sessions (token_hash TEXT PRIMARY KEY, expires INTEGER NOT NULL, created_at INTEGER NOT NULL)")
    db.commit()


def _hash(password, salt, iters):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iters).hex()


def has_admin(db):
    create_tables(db)
    return db.execute("SELECT 1 FROM bl_admin").fetchone() is not None


def username(db):
    create_tables(db)
    r = db.execute("SELECT username FROM bl_admin").fetchone()
    return r[0] if r else None


def create_admin(db, user, password, now=None):
    """Create the one admin. ValueError (with a plain message) for a bad name/password or when one already exists."""
    user = (user or "").strip()
    if not 1 <= len(user) <= 64 or not user.isprintable():
        raise ValueError("Pick a username (1 to 64 characters).")
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise ValueError("The password needs at least %d characters." % MIN_PASSWORD)
    if len(password) > 256:
        raise ValueError("The password is too long (256 characters at most).")
    if has_admin(db):
        raise ValueError("An admin already exists. Log in instead.")
    salt = secrets.token_hex(16)
    db.execute("INSERT INTO bl_admin (id, username, salt, pw_hash, iters, created_at) VALUES (1, ?, ?, ?, ?, ?)",
               (user, salt, _hash(password, salt, ITERATIONS), ITERATIONS, int(now or time.time())))
    db.commit()


def locked(ip, now=None):
    now = time.time() if now is None else now
    n, until = _fails.get(ip, (0, 0))
    return until > now


def note_fail(ip, now=None):
    """Count one wrong guess from `ip`; five lock it for a minute (same counter as wrong passwords)."""
    now = time.time() if now is None else now
    n, _until = _fails.get(ip, (0, 0))
    n += 1
    _fails[ip] = (0, now + LOCK_S) if n >= MAX_FAILS else (n, 0)


def clear_fails(ip):
    _fails.pop(ip, None)


def check_login(db, ip, user, password, now=None):
    """True when the credentials match. Five misses from one address lock it for a minute."""
    now = time.time() if now is None else now
    if locked(ip, now):
        return False
    create_tables(db)
    r = db.execute("SELECT username, salt, pw_hash, iters FROM bl_admin").fetchone()
    ok = False
    if r is not None and isinstance(password, str) and len(password) <= 256:
        calc = _hash(password, r[1], r[3])
        ok = hmac.compare_digest(calc, r[2]) and hmac.compare_digest((user or "").strip().encode(), r[0].encode())
    if ok:
        _fails.pop(ip, None)
        return True
    note_fail(ip, now)
    return False


def new_session(db, now=None):
    now = int(now or time.time())
    token = secrets.token_urlsafe(32)
    create_tables(db)
    db.execute("DELETE FROM bl_sessions WHERE expires < ?", (now,))
    db.execute("INSERT INTO bl_sessions (token_hash, expires, created_at) VALUES (?, ?, ?)",
               (hashlib.sha256(token.encode()).hexdigest(), now + SESSION_S, now))
    db.commit()
    return token


def session_ok(db, cookie_header, now=None):
    now = int(now or time.time())
    token = cookie_value(cookie_header, COOKIE)
    if not token:
        return False
    create_tables(db)
    r = db.execute("SELECT expires FROM bl_sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    return bool(r and r[0] >= now)


def end_session(db, cookie_header):
    token = cookie_value(cookie_header, COOKIE)
    if token:
        create_tables(db)
        db.execute("DELETE FROM bl_sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))
        db.commit()


def cookie_value(header, name):
    for part in (header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return ""


def cookie_header(token, secure=False, clear=False):
    attrs = "%s=%s; Path=/; HttpOnly; SameSite=Lax" % (COOKIE, "" if clear else token)
    attrs += "; Max-Age=0" if clear else "; Max-Age=%d" % SESSION_S
    return attrs + ("; Secure" if secure else "")


def auth_mode(db, env=None):
    env = os.environ if env is None else env
    if str(env.get("BLOOM_AUTH", "")).strip().lower() in ("off", "0", "false", "no", "none"):
        return "off"
    if has_admin(db):
        return "login"
    r = db.execute("SELECT v FROM acct_meta WHERE k = 'migration_legacy_defaults_v1'").fetchone() if _has_meta(db) else None
    return "lan" if r and r[0] == "1" else "setup"


def has_settings(db):
    """True when a time zone or electricity price is already on record (setup must then leave both alone)."""
    try:
        return db.execute("SELECT 1 FROM acct_settings WHERE key IN ('local_timezone', 'rate_schedule') LIMIT 1").fetchone() is not None
    except Exception:
        return False


def _has_meta(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE name = 'acct_meta'").fetchone() is not None


def setup_code_needed(client_is_private):
    """A client that is not on a private address must show the one-time code from the server log before it may create the admin.
    Initial setup from the local network is open by design."""
    return not client_is_private


def setup_code_ok(root, given):
    """True when `given` is the one-time code from the server log. Compared in constant time."""
    return hmac.compare_digest(str(given or "").strip().encode(), setup_code(root).encode())


def rotate_setup_code(root):
    """Forget the code once it has been used, so a copy of the old log line is worthless."""
    from pathlib import Path
    try:
        (Path(root) / "setup-code").unlink()
    except OSError:
        pass


def setup_code(root):
    """Read or create <data>/setup-code (a one-time code logged at start so only the person with log access can finish setup)."""
    from pathlib import Path
    p = Path(root) / "setup-code"
    try:
        c = p.read_text().strip()
        if c:
            return c
    except OSError:
        pass
    c = secrets.token_hex(6)
    p.write_text(c + "\n")
    try:
        p.chmod(0o600)
    except OSError:
        pass
    return c


def write_denied(db, client_ip, headers, lan_guard, env=None):
    """None when a write may go ahead, else (status, body). `lan_guard` is bloom_lan.write_guard bound to this request."""
    import bloom_lan
    mode = auth_mode(db, env)
    if mode in ("off", "lan"):
        return lan_guard()
    if mode == "setup":
        return (401, {"error": "setup required", "setup": True})
    if session_ok(db, headers.get("Cookie")):
        return None if bloom_lan.same_origin(headers) else (403, {"error": "cross-origin write blocked"})
    if bloom_lan.access_ok(headers, os.environ if env is None else env, None, time.time()) and bloom_lan.same_origin(headers):
        return None
    return (401, {"error": "login required", "login": True})
