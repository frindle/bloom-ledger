"""Frozen test: bloom_access.verify claim checks (iss, aud, claims shape). Helpers come from test_bloom_access."""
import bloom_access as A
from test_bloom_access import AUD, ISS, KEY, TEAM, check, make_token


def test_issuer_must_match_the_team_exactly():
    assert callable(A.verify)
    assert check(make_token(KEY)) is not None
    for iss in ("https://" + TEAM + ".evil.invalid", "https://" + TEAM + "/", "http://" + TEAM, "https://evil.example.invalid",
                "HTTPS://" + TEAM, " https://" + TEAM, [ISS], {"u": ISS}, 7, "", None):
        assert check(make_token(KEY, iss=iss)) is None, iss


def test_aud_string_or_list_must_contain_the_exact_tag():
    assert check(make_token(KEY, aud=AUD)) is not None
    assert check(make_token(KEY, aud=["other", AUD])) is not None
    for aud in (["other"], [], "", "x" + AUD, AUD + "x", AUD.upper(), ["x" + AUD], {AUD: 1}, {"aud": AUD}, 7, [[AUD]], None):
        assert check(make_token(KEY, aud=aud)) is None, aud


def test_claims_that_are_not_a_json_object_are_refused():
    for body in ([], [ISS], "text", 5, None):
        tok = make_token(KEY, body=body) if body is not None else make_token(KEY, body="null")
        assert check(tok) is None, body
