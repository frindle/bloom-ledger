"""Frozen test: bloom_access.verify (Cloudflare Access RS256 JWT, stdlib only). All keys are throwaway, no network."""
import base64
import hashlib
import hmac
import json
import random

import bloom_access as A

TEAM = "example-team.cloudflareaccess.com"
AUD = "fake-aud-tag-0001"
ISS = "https://" + TEAM
NOW = 1_800_000_000
DI = bytes.fromhex("3031300d060960864801650304020105000420")


def _prime(rnd, bits):
    while True:
        c = rnd.getrandbits(bits) | (1 << (bits - 1)) | 1
        if all(pow(a, c - 1, c) == 1 for a in (2, 3, 5, 7, 11, 13)):
            return c


def make_key(seed, bits=768):
    rnd = random.Random(seed)
    while True:
        p, q = _prime(rnd, bits // 2), _prime(rnd, bits // 2)
        if p == q:
            continue
        phi = (p - 1) * (q - 1)
        try:
            return p * q, pow(65537, -1, phi)
        except ValueError:
            continue


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def int_b64(n):
    return b64(n.to_bytes((n.bit_length() + 7) // 8, "big"))


def good_em(si, k):
    t = DI + hashlib.sha256(si).digest()
    return b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t


def sign_with(key, si, em_fn=good_em):
    n, d = key
    k = (n.bit_length() + 7) // 8
    return pow(int.from_bytes(em_fn(si.encode(), k), "big"), d, n).to_bytes(k, "big")


def make_token(key, kid="k1", head=None, body=None, sig=None, **over):
    """Build a signed token. head: header overrides (None value drops the key); body: replaces the whole payload;
    sig: raw signature bytes or a function (si_bytes, k) -> encoded block that is signed instead of the good one."""
    claims = {"iss": ISS, "aud": [AUD], "exp": NOW + 600, "email": "someone@example.invalid"}
    claims.update(over)
    hd = {"alg": "RS256", "kid": kid}
    hd.update(head or {})
    hd = {k: v for k, v in hd.items() if v is not None}
    payload = body if body is not None else {k: v for k, v in claims.items() if v is not None}
    si = b64(json.dumps(hd).encode()) + "." + b64(json.dumps(payload).encode())
    if sig is None:
        sig = sign_with(key, si)
    elif callable(sig):
        sig = sign_with(key, si, sig)
    return si + "." + b64(sig)


def jwks(*pairs):
    return {"keys": [{"kty": "RSA", "kid": kid, "alg": "RS256", "n": int_b64(k[0]), "e": "AQAB"} for kid, k in pairs]}


KEY = make_key(1)
OTHER = make_key(2)


def fetcher(doc, calls):
    def f(url):
        calls.append(url)
        if isinstance(doc, Exception):
            raise doc
        return doc
    return f


def check(token, doc=None, calls=None, team=TEAM, aud=AUD, now=NOW):
    A.reset_cache()
    calls = [] if calls is None else calls
    return A.verify(token, team, aud, fetcher(doc if doc is not None else jwks(("k1", KEY)), calls), now)


def hs256_token(secret):
    si = b64(json.dumps({"alg": "HS256", "kid": "k1"}).encode()) + "." + b64(json.dumps({"iss": ISS, "aud": [AUD], "exp": NOW + 600, "email": "someone@example.invalid"}).encode())
    return si + "." + b64(hmac.new(secret, si.encode(), hashlib.sha256).digest())


def test_only_rs256_with_a_string_kid_is_accepted():
    assert check(make_token(KEY)) is not None
    for head in ({"alg": "none"}, {"alg": "HS256"}, {"alg": "RS512"}, {"alg": "rs256"}, {"alg": None}, {"alg": ["RS256"]},
                 {"kid": None}, {"kid": 7}, {"kid": ["k1"]}):
        assert check(make_token(KEY, head=head)) is None


def test_hmac_tokens_keyed_with_the_public_key_are_refused():
    n_bytes = KEY[0].to_bytes((KEY[0].bit_length() + 7) // 8, "big")
    jwk_json = json.dumps(jwks(("k1", KEY))["keys"][0]).encode()
    for secret in (n_bytes, jwk_json, b""):
        assert check(hs256_token(secret)) is None


def test_malformed_tokens_and_non_string_input_refused():
    h, b, s = make_token(KEY).split(".")
    for bad in ("", "a.b", "a.b.c.d", "!!.!!.!!", h + "." + b, "." + b + "." + s, None, 42, b"x.y.z", [h, b, s]):
        assert check(bad) is None


def test_team_or_aud_unset_fails_closed_without_fetching():
    calls = []
    for team, aud in (("", AUD), (TEAM, ""), (None, AUD), (TEAM, None), ("", "")):
        assert check(make_token(KEY), calls=calls, team=team, aud=aud) is None
    assert calls == []


def test_good_token_fetches_team_certs_once_and_fetch_failure_refuses():
    calls = []
    claims = check(make_token(KEY), calls=calls)
    assert claims["email"] == "someone@example.invalid"
    assert claims["iss"] == ISS
    assert calls == ["https://" + TEAM + "/cdn-cgi/access/certs"]
    assert check(make_token(KEY), doc=OSError("down")) is None
    assert check(make_token(KEY), doc={"nokeys": 1}) is None
