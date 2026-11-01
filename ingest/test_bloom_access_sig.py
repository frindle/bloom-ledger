"""Frozen test: bloom_access.verify RS256 signature check (strict PKCS#1 v1.5 block, strict base64url). Helpers come from test_bloom_access."""
import base64
import hashlib

import bloom_access as A
from test_bloom_access import AUD, DI, KEY, NOW, OTHER, TEAM, b64, check, jwks, make_token

SHA1_DI = bytes.fromhex("3021300906052b0e03021a05000414")


def sha256_t(si):
    return DI + hashlib.sha256(si).digest()


def test_token_signed_by_another_key_or_tampered_is_refused():
    A.reset_cache()
    assert A.verify(make_token(OTHER), TEAM, AUD, lambda url: jwks(("k1", KEY)), NOW) is None
    assert check(make_token(KEY)) is not None
    h, b, s = make_token(KEY).split(".")
    forged = b64(b'{"iss": "https://%s", "aud": ["%s"], "exp": %d, "email": "x@example.invalid"}' % (TEAM.encode(), AUD.encode(), NOW + 600))
    assert check(h + "." + forged + "." + s) is None
    assert check(h + "." + b + "." + s[:-4] + "AAAA") is None
    assert check(h + "." + b + ".") is None
    assert check(make_token(KEY), doc={"keys": [{"kid": "k1", "kty": "RSA", "n": "!!", "e": "AQAB"}]}) is None


def test_every_bad_padding_block_carrying_the_right_hash_is_refused():
    k_pad = lambda si, k: k - 3 - len(sha256_t(si))
    blocks = {
        "no digestinfo": lambda si, k: b"\x00\x01" + b"\xff" * (k - 3 - 32) + b"\x00" + hashlib.sha256(si).digest(),
        "sha1 digestinfo": lambda si, k: b"\x00\x01" + b"\xff" * (k - 3 - 35) + b"\x00" + SHA1_DI + hashlib.sha1(si).digest(),
        "type 2": lambda si, k: b"\x00\x02" + b"\xff" * k_pad(si, k) + b"\x00" + sha256_t(si),
        "zero in ff run": lambda si, k: b"\x00\x01" + b"\xff" * 20 + b"\x00" + b"\xff" * (k_pad(si, k) - 21) + b"\x00" + sha256_t(si),
        "garbage after hash": lambda si, k: b"\x00\x01" + b"\xff" * (k_pad(si, k) - 6) + b"\x00" + sha256_t(si) + b"\x01\x02\x03\x04\x05\x06",
        "padding under 8 bytes": lambda si, k: b"\x00\x01" + b"\xff" * 7 + b"\x00" + sha256_t(si) + b"\xaa" * (k_pad(si, k) - 7),
        "no leading zero": lambda si, k: b"\x01" + b"\xff" * (k_pad(si, k) + 1) + b"\x00" + sha256_t(si),
    }
    assert check(make_token(KEY)) is not None
    for name, em in blocks.items():
        assert check(make_token(KEY, sig=em)) is None, name


def test_signature_must_be_exactly_the_modulus_length_and_below_n():
    n = KEY[0]
    k = (n.bit_length() + 7) // 8
    for i in range(1000):
        tok = make_token(KEY, exp=NOW + 600 + i)
        h, b, s = tok.split(".")
        raw = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
        if raw[0] == 0:
            break
    else:
        raise AssertionError("no token with a leading zero byte found")
    assert check(tok) is not None
    assert check(h + "." + b + "." + b64(raw[1:])) is None
    assert check(h + "." + b + "." + b64(b"\x00" + raw)) is None
    assert check(make_token(KEY, sig=n.to_bytes(k, "big"))) is None
    assert check(make_token(KEY, sig=b"\xff" * k)) is None


def test_base64url_segments_are_decoded_strictly():
    h, b, s = make_token(KEY).split(".")
    assert check(h + "." + b + "." + s) is not None
    for bad_s in (s + "=", s + "\n", s[:10] + "!" + s[10:], s[:10] + "+" + s[11:], s[:10] + "/" + s[11:], s + "A", " " + s):
        assert check(h + "." + b + "." + bad_s) is None
    for bad_h in (h + "=", h[:5] + "!" + h[5:], h + "\n"):
        assert check(bad_h + "." + b + "." + s) is None
