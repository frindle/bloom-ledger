"""Frozen test: the index schema and the dashboard summary carry no OpenTimestamps / Bitcoin state."""
import inspect
import re

import bloom_ingest as I
import bloom_ingest_ledger as IL
import bloom_ledger as L
import bloom_summary as S

NOW = 1793300000.0
OTS_WORDS = re.compile(r"opentimestamps|bitcoin|\.ots\b|\bots\b", re.I)


def test_open_db_creates_only_the_objects_table(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    names = sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'"))
    assert names == ["objects"], names


def test_summary_days_have_no_ots_field(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    I.index_object(db, "m4max", "log", "a" * 64, 10, NOW - 3 * 86400)
    day = I.utc_day(NOW - 3 * 86400)
    L.write_manifest(IL.ledger_dir(tmp_path, "m4max"), L.make_manifest(day, "m4max", [], None))
    days = S.summary(db, tmp_path, NOW)["machines"][0]["days"]
    assert set(days[0]) == {"day", "files", "bytes", "state", "chain_hash"}, sorted(days[0])
    assert [d["state"] for d in days] == ["sealed", "missing", "missing", "open"]


def test_modules_mention_no_ots_or_bitcoin():
    for mod in (S, I):
        hit = OTS_WORDS.search(inspect.getsource(mod))
        assert hit is None, (mod.__name__, hit and hit.group(0))
