"""Frozen test: admin_check no longer verifies a secret (step before it is deleted)."""
import inspect

import bloom_settings as S


def test_admin_check_has_no_secret_comparison_left():
    src = inspect.getsource(S.admin_check)
    assert "hmac" not in src and "compare_digest" not in src and "re.fullmatch" not in src


def test_admin_check_no_longer_reads_a_secret_file(tmp_path):
    assert S.admin_check({}, None) is None
    assert S.admin_check({"Authorization": "Bearer x"}, str(tmp_path / "missing")) == (401, {"error": "unauthorized"})
