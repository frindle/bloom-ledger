"""The resell-tracker export API is invisible unless enabled; old installs (migrated) keep it. Fake data."""
import sqlite3

import bloom_accounting_index as AX
import bloom_migrate as MIG
from server_fixture import web  # noqa: F401

PATHS = ["/v1/tally/months", "/v1/tally/monthly?month=2026-10", "/v1/invoice/months", "/v1/invoice/monthly?month=2026-10", "/v1/withdrawals"]


def test_off_by_default_is_a_plain_404(web, monkeypatch):
    monkeypatch.delenv("BLOOM_ENABLE_EXPORT_API", raising=False)
    for p in PATHS:
        s, _c, body = web("GET", p)
        assert s == 404 and b"not found" in body, p


def test_on_with_the_variable(web, monkeypatch):
    monkeypatch.setenv("BLOOM_ENABLE_EXPORT_API", "1")
    assert web("GET", "/v1/tally/months")[0] == 200
    assert web("GET", "/v1/withdrawals")[0] == 200


def test_migrated_install_keeps_it():
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    db.execute("INSERT INTO earnings (ledger_id, ts, micro_usd, kind, model, job_id, completion_tokens, source_machine)"
               " VALUES ('L1', 1791900000, 5, 'inference', 'm', 'j', 0, 'm1')")
    assert not MIG.export_api_enabled(db, {})
    MIG.run(db, lambda m: None)
    assert MIG.export_api_enabled(db, {})
    fresh = sqlite3.connect(":memory:")
    AX.create_schema(fresh)
    MIG.run(fresh, lambda m: None)
    assert not MIG.export_api_enabled(fresh, {})
