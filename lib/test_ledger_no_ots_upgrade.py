"""Frozen test: bloom_ledger no longer has ots_upgrade."""
import inspect

import bloom_ledger as L


def test_ots_upgrade_is_gone():
    assert not hasattr(L, "ots_upgrade")


def test_no_ots_upgrade_text_remains():
    src = inspect.getsource(L)
    assert "ots_upgrade" not in src and "ots upgrade" not in src and '"upgrade"' not in src
