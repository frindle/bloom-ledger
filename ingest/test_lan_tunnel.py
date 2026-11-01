"""Frozen test: bloom_lan.write_guard with a Cloudflare Access JWT on the tunnel path (fake team, throwaway key, no network)."""
import bloom_access as A
import bloom_lan as L
import test_bloom_access as T

ENV = {"BLOOM_ACCESS_TEAM_DOMAIN": T.TEAM, "BLOOM_ACCESS_AUD": T.AUD}
DOC = T.jwks(("k1", T.KEY))
HOST = "ledger.example.invalid"
TUNNEL = {"Origin": "https://" + HOST, "Host": HOST, "CF-Connecting-IP": "203.0.113.9", "X-Forwarded-For": "203.0.113.9"}
NOLOCAL = (403, {"error": "local network only"})


def guard(ip, headers, token=None, env=ENV, doc=DOC, now=T.NOW):
    A.reset_cache()
    h = dict(headers)
    if token is not None:
        h["Cf-Access-Jwt-Assertion"] = token

    def fetch(url):
        if isinstance(doc, Exception):
            raise doc
        return doc

    return L.write_guard(ip, h, env=env, fetch_jwks=fetch, now=now)


def test_tunnel_write_with_valid_token_is_allowed():
    assert guard("172.18.0.5", TUNNEL, T.make_token(T.KEY)) is None
    assert guard("8.8.8.8", TUNNEL, T.make_token(T.KEY)) is None


def test_tunnel_write_without_or_with_bad_token_is_refused():
    assert guard("172.18.0.5", TUNNEL) == NOLOCAL
    assert guard("172.18.0.5", TUNNEL, "") == NOLOCAL
    assert guard("172.18.0.5", TUNNEL, "garbage") == NOLOCAL
    assert guard("172.18.0.5", TUNNEL, T.make_token(T.OTHER)) == NOLOCAL
    assert guard("172.18.0.5", TUNNEL, T.make_token(T.KEY, aud=["x"])) == NOLOCAL
    assert guard("172.18.0.5", TUNNEL, T.make_token(T.KEY, exp=T.NOW - 5)) == NOLOCAL
    assert guard("172.18.0.5", TUNNEL, T.make_token(T.KEY, kid="zz")) == NOLOCAL
    assert guard("172.18.0.5", TUNNEL, T.make_token(T.KEY), doc=OSError("down")) == NOLOCAL


def test_env_unset_or_empty_keeps_tunnel_refused_even_with_valid_token():
    tok = T.make_token(T.KEY)
    assert guard("172.18.0.5", TUNNEL, tok, env={}) == NOLOCAL
    assert guard("172.18.0.5", TUNNEL, tok, env={"BLOOM_ACCESS_TEAM_DOMAIN": T.TEAM}) == NOLOCAL
    assert guard("172.18.0.5", TUNNEL, tok, env={"BLOOM_ACCESS_AUD": T.AUD}) == NOLOCAL
    assert guard("172.18.0.5", TUNNEL, tok, env={"BLOOM_ACCESS_TEAM_DOMAIN": "", "BLOOM_ACCESS_AUD": ""}) == NOLOCAL


def test_same_origin_still_applies_on_tunnel_path():
    tok = T.make_token(T.KEY)
    bad = dict(TUNNEL, Origin="https://evil.example")
    assert guard("172.18.0.5", bad, tok) == (403, {"error": "cross-origin write blocked"})
    noorigin = {k: v for k, v in TUNNEL.items() if k != "Origin"}
    assert guard("172.18.0.5", noorigin, tok) == (403, {"error": "cross-origin write blocked"})


def test_lan_behaviour_unchanged_with_and_without_env():
    lan = {"Origin": "http://10.0.0.5:8080", "Host": "10.0.0.5:8080"}
    for env in (ENV, {}):
        assert guard("10.0.0.7", lan, env=env) is None
        assert guard("8.8.8.8", lan, env=env) == NOLOCAL
        assert guard("10.0.0.7", dict(lan, **{"X-Forwarded-For": "8.8.8.8"}), env=env) == NOLOCAL
        assert guard("10.0.0.7", {"Origin": "http://evil.example", "Host": "10.0.0.5"}, env=env) == (403, {"error": "cross-origin write blocked"})
    assert guard("10.0.0.7", lan, T.make_token(T.KEY), doc=OSError("fetch must not run for LAN requests")) is None
    assert L.write_guard("10.0.0.7", {"Origin": "http://10.0.0.5:8080", "Host": "10.0.0.5:8080"}) is None
    assert L.write_guard("8.8.8.8", TUNNEL) == NOLOCAL
