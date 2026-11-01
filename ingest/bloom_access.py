"""Cloudflare Access JWT verification (RS256, stdlib only)."""
import base64
import hashlib
import json
import math
import urllib.request

TTL = 3600
RETRY = 60
DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
B64 = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
MAX_JWKS = 65536
_CACHE = {}
_ATTEMPT = {}


def reset_cache():
    _CACHE.clear()
    _ATTEMPT.clear()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def default_fetch(url):
    if not url.startswith("https://"):
        raise ValueError("https only")
    with _OPENER.open(url, timeout=5) as r:
        data = r.read(MAX_JWKS + 1)
    if len(data) > MAX_JWKS:
        raise ValueError("jwks too large")
    return json.loads(data.decode())


def _b64d(s):
    if not set(s) <= B64 or len(s) % 4 == 1:
        raise ValueError("bad base64url")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _load_keys(team, fetch_jwks, now):
    doc = fetch_jwks("https://" + team + "/cdn-cgi/access/certs")
    keys = {}
    for k in doc["keys"]:
        try:
            if k.get("kty") == "RSA" and isinstance(k.get("kid"), str) and k["kid"]:
                keys[k["kid"]] = (int.from_bytes(_b64d(k["n"]), "big"), int.from_bytes(_b64d(k["e"]), "big"))
        except Exception:
            continue
    _CACHE[team] = (now, keys)
    return keys


def _key_for(team, kid, fetch_jwks, now):
    hit = _CACHE.get(team)
    if hit and now - hit[0] < TTL and kid in hit[1]:
        return hit[1][kid]
    last = _ATTEMPT.get(team)
    if last is not None and now - last < RETRY:
        return None
    _ATTEMPT[team] = now
    return _load_keys(team, fetch_jwks, now).get(kid)


def _rs256_ok(n, e, signing_input, sig):
    k = (n.bit_length() + 7) // 8
    if len(sig) != k or int.from_bytes(sig, "big") >= n:
        return False
    t = DIGEST_INFO + hashlib.sha256(signing_input).digest()
    if k < len(t) + 11:
        return False
    em = pow(int.from_bytes(sig, "big"), e, n).to_bytes(k, "big")
    return em == b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def verify(token, team_domain, aud, fetch_jwks, now):
    """Return the claims dict for a valid Access token, else None. Never raises."""
    try:
        if not team_domain or not aud or not isinstance(token, str):
            return None
        parts = token.split(".")
        if len(parts) != 3:
            return None
        head = json.loads(_b64d(parts[0]))
        if head.get("alg") != "RS256" or not isinstance(head.get("kid"), str):
            return None
        key = _key_for(team_domain, head["kid"], fetch_jwks, now)
        if key is None:
            return None
        if not _rs256_ok(key[0], key[1], (parts[0] + "." + parts[1]).encode(), _b64d(parts[2])):
            return None
        claims = json.loads(_b64d(parts[1]))
        if claims.get("iss") != "https://" + team_domain:
            return None
        a = claims["aud"]
        if aud not in (a if isinstance(a, list) else [a]):
            return None
        if not _num(claims.get("exp")) or claims["exp"] <= now:
            return None
        if "nbf" in claims and (not _num(claims["nbf"]) or claims["nbf"] > now):
            return None
        if not isinstance(claims.get("email"), str) or not claims["email"]:
            return None
        return claims
    except Exception:
        return None
