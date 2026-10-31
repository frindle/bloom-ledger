"""Frozen test: bloom_ledger no longer has ots_stamp or its OpenTimestamps section."""
import inspect

import bloom_ledger as L


def test_ots_stamp_is_gone():
    assert not hasattr(L, "ots_stamp")


def test_stamp_function_text_is_gone():
    src = inspect.getsource(L)
    for word in ("ots_stamp", '"stamp"', ".ots", "run=subprocess.run", "SubprocessError"):
        assert word not in src, word
    assert src.count("OpenTimestamps") == 1  # only the module docstring line is left for the next step
