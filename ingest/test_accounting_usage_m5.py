"""Frozen test: bloom_accounting_usage.m5_business_bp / personal_token_share."""
import bloom_accounting_usage as U


def test_m5_business_bp():
    assert U.m5_business_bp(1000, 0) == 10000
    assert U.m5_business_bp(1000, 250) == 7500
    assert U.m5_business_bp(3, 1) == 6666
    assert U.m5_business_bp(1000, 5000) == 0
    assert U.m5_business_bp(1000, -5) == 10000
    assert U.m5_business_bp(0, 0) == 0


def test_personal_token_share_prorates_total_tokens():
    assert U.personal_token_share(1000, 250, 1000) == 250
    assert U.personal_token_share(1000, 0, 1000) == 0
    assert U.personal_token_share(10, 1, 3) == 3
    assert U.personal_token_share(1000, 5000, 1000) == 1000
    assert U.personal_token_share(1000, 5, 0) == 0
