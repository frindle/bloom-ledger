"""Frozen test: bloom_accounting_index.store_earnings (synthetic rows)."""
import json

import bloom_accounting_index as A
import bloom_ingest as I


def row(i, ts="2026-10-20T12:00:00Z", amt=100, **kw):
    d = {"_id": i, "created_at": ts, "amount_micro_usd": amt, "model": "m", "job_id": "j" + i}
    d.update(kw)
    return json.dumps(d)


def mk(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    return db


def test_dedupe_across_objects_and_machines(tmp_path):
    db = mk(tmp_path)
    assert A.store_earnings(db, "m1", "a" * 64, row("L1") + "\n" + row("L2") + "\n") == (2, 0)
    assert A.store_earnings(db, "m2", "b" * 64, row("L2") + "\n" + row("L3")) == (1, 0)
    assert db.execute("SELECT COUNT(*), SUM(micro_usd) FROM earnings").fetchone() == (3, 300)
    assert db.execute("SELECT source_machine FROM earnings WHERE ledger_id='L2'").fetchone()[0] == "m1"


def test_bad_lines_counted_and_early_rows_skipped(tmp_path):
    db = mk(tmp_path)
    assert A.INGEST_FROM_TS == 1791849600  # 2026-10-13 UTC
    payload = "\n".join([row("L1"), "junk", "", row("L2", amt=-5), row("OLD", ts="2026-10-12T23:59:59Z")])
    assert A.store_earnings(db, "m1", "c" * 64, payload) == (1, 2)
    assert db.execute("SELECT n FROM acct_parse_errors WHERE machine_id='m1' AND sha256=?", ("c" * 64,)).fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM earnings WHERE ledger_id='OLD'").fetchone()[0] == 0
    assert A.store_earnings(db, "m1", "d" * 64, row("OLD", ts="2026-10-12T23:59:59Z"), since_ts=0) == (1, 0)
