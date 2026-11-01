"""Frozen test: bloom_access.verify exp / nbf / email checks. Helpers come from test_bloom_access."""
import bloom_access as A
from test_bloom_access import KEY, NOW, check, make_token


def test_exp_must_be_a_finite_number_still_in_the_future():
    assert callable(A.verify)
    assert check(make_token(KEY, exp=NOW + 1)) is not None
    assert check(make_token(KEY, exp=float(NOW + 1))) is not None
    for exp in (NOW, NOW - 1, True, "9999999999", float("inf"), float("nan"), None, [NOW + 600], {"x": 1}):
        assert check(make_token(KEY, exp=exp)) is None, exp


def test_nbf_when_present_must_be_a_number_not_in_the_future():
    assert check(make_token(KEY, nbf=NOW - 60)) is not None
    assert check(make_token(KEY, nbf=NOW)) is not None
    for nbf in (NOW + 60, "x", "0", True, [0], float("inf")):
        assert check(make_token(KEY, nbf=nbf)) is None, nbf


def test_email_must_be_a_non_empty_string():
    for email in (None, "", 7, ["a@example.invalid"], {"e": 1}):
        assert check(make_token(KEY, email=email)) is None, email
