"""Frozen test: day rows and period totals carry Darkbloom GPU, Sandbox and whole-machine bytes in and out. Fake data."""
import bloom_accounting_index as A
import bloom_accounting_report as RP
import bloom_ingest as I

T0 = 1796083200  # 2026-12-01T00:00:00Z
DAY = 86400
NET = ("gpu_bytes_in", "gpu_bytes_out", "sandbox_bytes_in", "sandbox_bytes_out", "total_bytes_in", "total_bytes_out")


def add(row, net):
    assert hasattr(RP, "add_net_bytes"), "bloom_accounting_report has no add_net_bytes"
    RP.add_net_bytes(row, net)


def test_add_net_bytes():
    row = {c: 0 for c in NET}
    row["net_minutes"] = 0
    add(row, [10, 20, 30, 40, 100, 200])
    add(row, [None, None, None, None, None, None])
    add(row, [1, None, 0, 2, 5, None])
    assert [row[c] for c in NET] == [11, 20, 30, 42, 105, 200]
    assert row["net_minutes"] == 2, "a minute with no measured total_bytes_in is not counted"
    row2 = {c: 0 for c in NET}
    row2["net_minutes"] = 0
    add(row2, [7, 7, 7, 7, None, 9])
    assert row2["net_minutes"] == 0 and row2["total_bytes_out"] == 9 and row2["gpu_bytes_in"] == 7


def test_day_rows_and_totals(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    mins = [("m1", T0, 1, (100, 1000, 0, 0, 150, 1100)),
            ("m1", T0 + 60, 0, (5, 6, 7, 8, 30, 40)),             # bad power reading: bytes still count
            ("m1", T0 + 120, 1, (None, None, None, None, None, None)),
            ("m1", T0 + DAY, 1, (0, 0, 2000, 3000, 2500, 3500)),
            ("m2", T0 + DAY + 60, 1, (9, 9, 9, 9, 9, 9))]
    for m, ts, ok, net in mins:
        db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, other_work, tokens_delta, sandbox_jobs, "
                   + ", ".join(NET) + ") VALUES (?, ?, 1.0, 60, ?, 0, 0, 0" + ", ?" * 6 + ")", (m, ts, ok, *net))
    db.commit()
    rows = RP.day_rows(db, "UTC", "2026-12-01", "2026-12-02", "m1")
    assert [r["date"] for r in rows] == ["2026-12-02", "2026-12-01"]
    assert all(c in rows[0] for c in NET + ("net_minutes",)), sorted(rows[0])
    new, old = rows
    assert [old[c] for c in NET] == [105, 1006, 7, 8, 180, 1140] and old["net_minutes"] == 2
    assert [new[c] for c in NET] == [0, 0, 2000, 3000, 2500, 3500] and new["net_minutes"] == 1
    t = RP.totals(rows)
    assert [t[c] for c in NET] == [105, 1006, 2007, 3008, 2680, 4640] and t["net_minutes"] == 3
    both = RP.totals(RP.day_rows(db, "UTC", "2026-12-01", "2026-12-02"))
    assert both["total_bytes_in"] == 2689 and both["net_minutes"] == 4
    assert RP.totals([{"date": "x", "earned_micro": 0, "tokens": 0, "wh": 0.0, "minutes": 0, "paid_minutes": 0,
                       "cost_micro": 0}])["total_bytes_out"] == 0, "a row without byte keys adds nothing"


def test_internet_minutes_are_counted_apart_from_older_all_traffic_minutes(tmp_path):
    row = {c: 0 for c in NET}
    row["net_minutes"] = row["net_internet_minutes"] = 0
    RP.add_net_bytes(row, [1, 1, 1, 1, 5, 5], "internet")
    RP.add_net_bytes(row, [1, 1, 1, 1, 5, 5], "all")
    RP.add_net_bytes(row, [1, 1, 1, 1, 5, 5], None)
    RP.add_net_bytes(row, [1, 1, 1, 1, None, None], "internet")      # not measured: counts in neither
    assert row["net_minutes"] == 3 and row["net_internet_minutes"] == 1


def test_scope_flows_from_the_sidecar_to_the_day_row(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    for ts in (T0, T0 + 60, T0 + 120):
        db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, other_work, tokens_delta, sandbox_jobs)"
                   " VALUES ('m1', ?, 1.0, 60, 1, 0, 0, 0)", (ts,))
    db.commit()
    A.store_net(db, "m1", "ts_utc,gpu_bytes_in,gpu_bytes_out,sandbox_bytes_in,sandbox_bytes_out,total_bytes_in,total_bytes_out\n"
                          "2026-12-01T00:00:00Z,1,1,1,1,100,100\n"
                          "ts_utc,gpu_bytes_in,gpu_bytes_out,sandbox_bytes_in,sandbox_bytes_out,total_bytes_in,total_bytes_out,net_scope\n"
                          "2026-12-01T00:01:00Z,1,1,1,1,10,10,internet\n"
                          "2026-12-01T00:02:00Z,1,1,1,1,10,10,internet\n")
    day = RP.day_rows(db, "UTC", "2026-12-01", "2026-12-01")[0]
    assert day["net_minutes"] == 3 and day["net_internet_minutes"] == 2 and day["total_bytes_in"] == 120
    assert RP.totals([day])["net_internet_minutes"] == 2


def test_an_index_stored_before_the_scope_column_is_upgraded_in_place(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    for t in ("power_minutes", "net_bridge"):
        db.execute(f"ALTER TABLE {t} DROP COLUMN net_scope")
    A.create_schema(db)
    for t in ("power_minutes", "net_bridge"):
        assert "net_scope" in [r[1] for r in db.execute(f"PRAGMA table_info({t})")]
