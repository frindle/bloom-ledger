"""Frozen test: bloom_alerts no longer knows about OpenTimestamps or Bitcoin."""
import inspect

import bloom_alerts as AL


def test_evaluate_alerts_has_no_ots_threshold():
    params = list(inspect.signature(AL.evaluate_alerts).parameters)
    assert params == ["db", "now", "silent_s", "ring_s"], params


def test_no_ots_constant_or_upgrade_recorder():
    assert not hasattr(AL, "OTS_S"), "the OTS_S threshold constant is gone"
    assert not hasattr(AL, "record_upgrades"), "record_upgrades is gone"


def test_module_text_mentions_no_ots_or_bitcoin():
    src = inspect.getsource(AL).lower()
    for word in ("opentimestamps", "bitcoin", "ots-not-upgraded", "ots_s", "upgraded_at"):
        assert word not in src, word
