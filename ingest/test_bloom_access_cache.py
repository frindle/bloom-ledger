"""Frozen test: bloom_access.verify JWKS cache (cold fetch once, 1h TTL, unknown-kid refetch at most once per 60s per team). Helpers come from test_bloom_access."""
import bloom_access as A
from test_bloom_access import AUD, KEY, NOW, OTHER, TEAM, check, jwks, make_token

URL = "https://" + TEAM + "/cdn-cgi/access/certs"


def verifier(docs):
    calls = []

    def f(url):
        calls.append(url)
        return docs[min(len(calls) - 1, len(docs) - 1)]

    return f, calls


def test_cold_cache_fetches_exactly_once_for_a_known_or_unknown_kid():
    f, calls = verifier([jwks(("k1", KEY))])
    A.reset_cache()
    assert A.verify(make_token(KEY), TEAM, AUD, f, NOW) is not None
    assert calls == [URL]
    f, calls = verifier([jwks(("old", OTHER))])
    A.reset_cache()
    assert A.verify(make_token(KEY), TEAM, AUD, f, NOW) is None
    assert calls == [URL]


def test_cached_keys_are_reused_for_an_hour_then_refetched():
    f, calls = verifier([jwks(("k1", KEY))])
    A.reset_cache()
    assert A.verify(make_token(KEY), TEAM, AUD, f, NOW) is not None
    assert A.verify(make_token(KEY, exp=NOW + 9000), TEAM, AUD, f, NOW + 3599) is not None
    assert len(calls) == 1
    assert A.verify(make_token(KEY, exp=NOW + 9000), TEAM, AUD, f, NOW + 3600) is not None
    assert len(calls) == 2


def test_unknown_kid_refetches_at_most_once_per_minute_per_team():
    f, calls = verifier([jwks(("old", OTHER)), jwks(("old", OTHER), ("k1", KEY))])
    A.reset_cache()
    assert A.verify(make_token(KEY), TEAM, AUD, f, NOW) is None
    assert len(calls) == 1
    for dt in (1, 30, 59):
        assert A.verify(make_token(KEY), TEAM, AUD, f, NOW + dt) is None
    assert len(calls) == 1
    assert A.verify(make_token(KEY), TEAM, AUD, f, NOW + 60) is not None
    assert len(calls) == 2
    assert A.verify(make_token(KEY, kid="nope"), TEAM, AUD, f, NOW + 61) is None
    assert len(calls) == 2


def test_cache_is_per_team():
    f, calls = verifier([jwks(("k1", KEY))])
    A.reset_cache()
    assert A.verify(make_token(KEY), TEAM, AUD, f, NOW) is not None
    other_team = "other-team.cloudflareaccess.com"
    assert A.verify(make_token(KEY, iss="https://" + other_team), other_team, AUD, f, NOW + 1) is not None
    assert calls == [URL, "https://" + other_team + "/cdn-cgi/access/certs"]
