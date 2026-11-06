"""Per-minute CPU / GPU use (2026-11-06): the usage sidecar fills power_minutes, and the "usage" business share counts
each paid minute's Darkbloom + Sandbox part of its attributable energy instead of the whole minute."""
import datetime as dt
import sqlite3

import bloom_accounting_index as A
import bloom_accounting_report as RP
import bloom_accounting_writeoff as WO

TZ = "America/Los_Angeles"
HDR = "ts_utc," + ",".join(A.USAGE_COLUMNS)
T1, T2 = 1793692982, 1793693042          # 2026-11-03T08:03:02Z, 08:04:02Z


def mk():
    db = sqlite3.connect(":memory:")
    A.create_schema(db)
    return db


def usage(db, ts):
    return dict(zip(A.USAGE_COLUMNS, db.execute("SELECT " + ", ".join(A.USAGE_COLUMNS)
                                                + " FROM power_minutes WHERE ts = ?", (ts,)).fetchone()))


def u(**kw):
    base = {c: 0 for c in A.USAGE_COLUMNS}
    base.update(kw)
    return base


# ---------------------------------------------------------------- index
def test_usage_value():
    assert A.usage_value({"usage_s": "60.04"}, "usage_s") == 60.04
    assert A.usage_value({"dbk_cpu_ms": "12.6"}, "dbk_cpu_ms") == 13
    assert A.usage_value({"dbk_local": "1"}, "dbk_local") == 1 and A.usage_value({"dbk_local": "0"}, "dbk_local") == 0
    for bad in ("", " ", "abc", "-1", "nan", "inf"):
        assert A.usage_value({"gpu_mj": bad}, "gpu_mj") is None, bad
    assert A.usage_value({}, "gpu_mj") is None
    assert A.INDEX_VERSION == "6"
    assert A.route("power/usage-2026-11.csv") == "usage"


def test_sidecar_fills_power_minutes_in_either_order():
    side = (HDR + "\n" + "2026-11-03T08:03:02Z,60.0,1000,2000,3000,,,,500,600,700,800,9000,90000,1\n"
            + "2026-11-03T08:04:02Z,60.1,,,,,,,,,,,,,\n")
    P = "INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok) VALUES (?, ?, 1.0, 60, 1)"
    db = mk()
    db.execute(P, ("m4", T1))
    A.store_usage(db, "m4", side)
    db.execute(P, ("m4", T2))
    A.apply_usage_bridge(db)
    got = usage(db, T1)
    assert got["usage_s"] == 60.0 and got["dbk_cpu_ms"] == 1000 and got["dbk_gpu_ms"] == 3000
    assert got["sbx_cpu_ms"] is None and got["own_cpu_mj"] == 600 and got["gpu_mj"] == 90000 and got["dbk_local"] == 1
    assert usage(db, T2)["usage_s"] == 60.1 and usage(db, T2)["dbk_cpu_ms"] is None
    db2 = mk()
    A.store_usage(db2, "m4", side)
    db2.execute(P, ("m4", T1))
    A.apply_usage_bridge(db2)
    assert usage(db2, T1) == got
    db2.execute(P, ("m9", T2))
    A.apply_usage_bridge(db2)
    assert usage(db2, T2)["usage_s"] is None, "another machine's sidecar never fills this minute"


# ---------------------------------------------------------------- write-off rules
def test_usage_share_mode_validates_and_describes():
    r = WO.rules({"write_off": {"share": "usage"}})
    assert r["share"] == "usage"
    assert WO.validate({"share": "usage"}) == []
    assert WO.validate({"share": "bogus"}) == ["share must be measured, usage or fixed"]
    assert "CPU and GPU" in WO.describe(r)[2]
    assert WO.rules({"write_off": {"share": "nope"}})["share"] == "measured", "unknown share falls back to the default"


def test_usage_energy_splits_gpu_by_time_and_keeps_cpu_energy():
    e = WO.usage_energy(u(dbk_cpu_mj=1000, sbx_cpu_mj=200, own_cpu_mj=800, dbk_gpu_ms=30000, sbx_gpu_ms=0,
                          own_gpu_ms=10000, sys_gpu_ms=10000, gpu_mj=50000))
    assert e == {"darkbloom": 1000 + 30000, "sandbox": 200, "own": 800 + 10000}
    assert WO.usage_energy(u(dbk_cpu_mj=5, gpu_mj=900)) == {"darkbloom": 5, "sandbox": 0, "own": 0}, "idle GPU: no split"
    assert WO.usage_energy(u(dbk_cpu_mj=None)) is None and WO.usage_energy(u(gpu_mj=None)) is None
    assert WO.usage_energy(None) is None and WO.usage_energy({}) is None
    local = WO.usage_energy(u(dbk_cpu_mj=100, own_cpu_mj=50, dbk_local=1))
    assert local == {"darkbloom": 0, "sandbox": 0, "own": 150}, "own requests to the local endpoint are own use"


def test_minute_business():
    r = WO.rules({"write_off": {"share": "usage"}})
    heavy_own = u(dbk_cpu_mj=1000, own_cpu_mj=3000, gpu_mj=0)
    assert WO.minute_business(r, "other", "serving", True, heavy_own) == 0.25, "own work beside paid work: its part"
    assert WO.minute_business(r, "gpu", "serving", True, heavy_own) == 0.25
    assert WO.minute_business(r, "gpu", "serving", True, u(dbk_cpu_mj=None)) == 1.0, "not measured: whole minute"
    assert WO.minute_business(r, "gpu", "serving", True, u()) == 1.0, "nothing attributable: whole minute"
    assert WO.minute_business(r, "idle", "idle", False, heavy_own) == 0.0, "unpaid minutes stay whole-minute rules"
    own_on = WO.rules({"write_off": {"share": "usage", "count": {"own": True}}})
    assert WO.minute_business(own_on, "gpu", "serving", True, heavy_own) == 1.0
    measured = WO.rules(None)
    assert WO.minute_business(measured, "other", "serving", True, heavy_own) == 0.0, "default rules unchanged"
    assert WO.minute_business(measured, "gpu", "serving", True, heavy_own) == 1.0


# ---------------------------------------------------------------- report
def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def report_db():
    db = mk()
    cols = ["machine_id", "ts", "wh", "interval_s", "power_ok", "other_work", "tokens_delta", *A.USAGE_COLUMNS]
    sql = "INSERT INTO power_minutes (" + ", ".join(cols) + ") VALUES (" + ", ".join("?" * len(cols)) + ")"
    rows = [
        # Darkbloom serving while Penn works hard: 1/4 of attributable energy is Darkbloom's
        (utc(2026, 10, 20, 20, 0), 1.0, 1, 5, u(usage_s=60, dbk_cpu_mj=1000, own_cpu_mj=3000)),
        # Darkbloom alone, measured
        (utc(2026, 10, 20, 20, 1), 1.0, 0, 5, u(usage_s=60, dbk_cpu_mj=1000)),
        # Darkbloom, not measured (older sampler): whole minute
        (utc(2026, 10, 20, 20, 2), 1.0, 0, 5, {c: None for c in A.USAGE_COLUMNS}),
        # own only, no paid work
        (utc(2026, 10, 20, 20, 3), 1.0, 1, 0, u(usage_s=60, own_cpu_mj=900)),
    ]
    for ts, wh, other, tok, us in rows:
        db.execute(sql, ("m4", ts, wh, 60, 1, other, tok, *[us[c] for c in A.USAGE_COLUMNS]))
    db.commit()
    return db


def test_day_rows_fractional_business_minutes_under_usage_share():
    s = {"write_off": {"share": "usage"}}
    d = RP.day_rows(report_db(), TZ, "2026-10-20", "2026-10-20", settings=s)[0]
    assert d["business_minutes"] == 0.25 + 1.0 + 1.0 + 0.0
    assert d["usage_minutes"] == 3 and d["dbk_mj"] == 2000 and d["own_mj"] == 3900 and d["sbx_mj"] == 0
    old = RP.day_rows(report_db(), TZ, "2026-10-20", "2026-10-20", settings={})[0]
    assert old["business_minutes"] == 2.0, "measured (whole minutes) is unchanged: the mixed minute counts 0"
    t = RP.totals([d, d])
    assert t["usage_minutes"] == 6 and t["dbk_mj"] == 4000 and t["own_mj"] == 7800
