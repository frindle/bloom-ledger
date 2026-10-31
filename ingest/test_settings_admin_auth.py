"""Frozen test: bloom_settings.admin_check (Bearer admin token against the bloom_admin secret file)."""
import hashlib

import bloom_settings as S

TOKEN = "fixture-admin-token-0123456789abcdef"
DISABLED = (403, {"error": "admin disabled"})
DENIED = (401, {"error": "unauthorized"})


def secret(tmp_path, text):
    p = tmp_path / "bloom_admin"
    p.write_text(text)
    return str(p)


def bearer(tok):
    return {"Authorization": "Bearer " + tok}


def test_missing_or_blank_secret_disables_admin(tmp_path):
    assert S.admin_check(bearer(TOKEN), str(tmp_path / "absent")) == DISABLED
    assert S.admin_check(bearer(TOKEN), secret(tmp_path, "")) == DISABLED
    assert S.admin_check(bearer(""), secret(tmp_path, " \n")) == DISABLED
    assert S.admin_check({}, str(tmp_path / "absent")) == DISABLED


def test_plain_secret_accepts_the_matching_bearer(tmp_path):
    p = secret(tmp_path, TOKEN + "\n")
    assert S.admin_check(bearer(TOKEN), p) is None
    assert S.admin_check(bearer(TOKEN + "x"), p) == DENIED


def test_sha256_secret_accepts_the_matching_bearer(tmp_path):
    digest = hashlib.sha256(TOKEN.encode()).hexdigest()
    assert S.admin_check(bearer(TOKEN), secret(tmp_path, digest + "\n")) is None
    assert S.admin_check(bearer(TOKEN), secret(tmp_path, digest.upper())) is None
    assert S.admin_check(bearer(digest), secret(tmp_path, digest)) is None, "a plain 64-hex secret is accepted as is"
    assert S.admin_check(bearer("wrong"), secret(tmp_path, digest)) == DENIED


def test_missing_or_malformed_authorization_is_denied(tmp_path):
    p = secret(tmp_path, TOKEN)
    assert S.admin_check({}, p) == DENIED
    assert S.admin_check({"Authorization": "Basic " + TOKEN}, p) == DENIED
    assert S.admin_check({"Authorization": TOKEN}, p) == DENIED
    assert S.admin_check({"Authorization": "Bearer "}, p) == DENIED
    assert S.admin_check({"Authorization": "Bearer   "}, p) == DENIED


def test_token_is_never_echoed_in_the_result(tmp_path):
    p = secret(tmp_path, TOKEN)
    for headers in (bearer("guess-" + TOKEN), {}):
        res = S.admin_check(headers, p)
        assert res == DENIED and TOKEN not in repr(res) and "guess" not in repr(res)
    assert S.admin_check(bearer(TOKEN), p) is None
