"""Frozen test: the sampler's per-minute inference_active_frac is kept on power_minutes as active_frac (0..1, None = not measured)."""
import sqlite3

import bloom_accounting_index as A
import bloom_ingest as I

P = "power/power-log-2026-12.csv"
HDR = ",".join(A.LEGACY_POWER_COLUMNS)


def line(ts, frac):
    return f"{ts},60,60,1,150,200,2.0,1,serving,{frac},1,10,m,0,50,0,,"


def fracs(db):
    assert "active_frac" in [r[1] for r in db.execute("PRAGMA table_info(power_minutes)")], "power_minutes has no active_frac column"
    return [r[0] for r in db.execute("SELECT active_frac FROM power_minutes ORDER BY ts")]


def af(text, cols):
    r = A.parse_power_line(text, cols)
    assert r is not None, "the minute was dropped"
    assert "active_frac" in r, "parse_power_line returns no active_frac"
    return r["active_frac"]


def test_active_frac_parsed_and_clamped():
    cols = A.LEGACY_POWER_COLUMNS
    assert af(line("2026-12-01T00:00:00Z", "0.25"), cols) == 0.25
    assert af(line("2026-12-01T00:00:00Z", ""), cols) is None
    assert af(line("2026-12-01T00:00:00Z", "1.7"), cols) == 1.0
    assert af(line("2026-12-01T00:00:00Z", "-0.2"), cols) == 0.0
    assert af(line("2026-12-01T00:00:00Z", "abc"), cols) is None, "a bad fraction does not drop the minute"
    assert af(line("2026-12-01T00:00:00Z", "nan"), cols) is None
    no_col = [c for c in cols if c != "inference_active_frac"]
    short = "2026-12-01T00:00:00Z,60,60,1,150,200,2.0,1,serving,1,10,m,0,50,0,,"
    assert af(short, no_col) is None


def test_active_frac_stored_and_old_index_rebuilds(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    body = HDR + "\n" + line("2026-12-01T00:00:00Z", "0.5") + "\n" + line("2026-12-01T00:01:00Z", "") + "\n"
    assert A.store_power(db, "m1", "a" * 64, P, 0, body) == (2, 0)
    assert fracs(db) == [0.5, None]
    assert A.INDEX_VERSION == "5"
    old = sqlite3.connect(":memory:")
    old.execute("CREATE TABLE acct_meta (k TEXT PRIMARY KEY, v TEXT)")
    old.execute("INSERT INTO acct_meta VALUES ('index_version', '4')")
    old.execute("CREATE TABLE power_minutes (machine_id TEXT NOT NULL, ts INTEGER NOT NULL, wh REAL, PRIMARY KEY (machine_id, ts))")
    old.execute("INSERT INTO power_minutes VALUES ('m1', 1, 2.0)")
    A.create_schema(old)
    assert "active_frac" in [r[1] for r in old.execute("PRAGMA table_info(power_minutes)")]
    assert old.execute("SELECT COUNT(*) FROM power_minutes").fetchone()[0] == 0, "old derived rows are rebuilt from raw objects"
    assert old.execute("SELECT v FROM acct_meta WHERE k = 'index_version'").fetchone()[0] == "5"
