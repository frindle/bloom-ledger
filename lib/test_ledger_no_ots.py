"""Frozen test: bloom_ledger has no OpenTimestamps code (ots_stamp, ots_upgrade, ots-status.jsonl)."""
import inspect
import re

import bloom_ledger as L

BANNED = re.compile(r"opentimestamps|bitcoin|\bots\b|ots_|_ots|\.ots\b|ots-status|subprocess", re.I)


def test_ots_functions_are_gone():
    for name in ("_ots_log",):
        assert not hasattr(L, name), name


def test_module_text_mentions_no_ots_bitcoin_or_subprocess():
    hit = BANNED.search(inspect.getsource(L))
    assert hit is None, hit and hit.group(0)


def test_docstring_describes_only_the_hash_chain():
    doc = L.__doc__
    assert "hash-chained to the previous day's manifest" in doc
    assert "Used by bloom-manifest.py." in doc
    assert "OpenTimestamps" not in doc and "`ots`" not in doc
