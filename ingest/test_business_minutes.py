"""Frozen test: the business-use share counts only paid-job minutes (Darkbloom GPU or Sandbox); idle and own-work minutes count nothing. Fake data."""
import bloom_accounting_index as A
import bloom_accounting_report as RP
import bloom_ingest as I

T0 = 1796083200  # 2026-12-01T00:00:00Z


def share(*a):
    assert hasattr(RP, "business_share"), "bloom_accounting_report has no business_share"
    return RP.business_share(*a)


def test_share_per_minute():
    assert share("gpu", "serving", None) == 1.0 and share("sandbox", "idle", 0.0) == 1.0
    assert share("idle", "idle", None) == 0.0 and share("idle", "serving", 0.0) == 0.0, "online and waiting is not business time"
    assert share("idle", "off", None) == 0.0 and share("idle", "", None) == 0.0 and share("idle", None, None) == 0.0
    assert share("other", "serving", 0.4) == 0.0 and share("other", "idle", None) == 0.0, "own work is personal even with inference alongside"
    assert share("gap", "serving", 1.0) == 0.0


def test_day_and_period_share(tmp_path):
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    rows = [(0, 1, "serving", 0, 50, 0, 0.9),   # Darkbloom work
            (1, 1, "idle", 0, 0, 0, None),      # online, waiting for work
            (2, 1, "off", 0, 0, 0, None),       # Darkbloom off
            (3, 1, "serving", 1, 0, 0, 0.5),    # Penn's own work while half the minute served inference
            (4, 0, "serving", 0, 0, 0, None)]   # no power reading
    for i, ok, state, other, tok, sbx, frac in rows:
        db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, dbk_state, other_work, tokens_delta,"
                   " sandbox_jobs, active_frac) VALUES ('m1', ?, 1.0, 60, ?, ?, ?, ?, ?, ?)", (T0 + 60 * i, ok, state, other, tok, sbx, frac))
    db.commit()
    day = RP.day_rows(db, "UTC", "2026-12-01", "2026-12-01")
    assert len(day) == 1 and day[0]["minutes"] == 4 and day[0]["paid_minutes"] == 1
    assert day[0].get("business_minutes") == 1.0
    t = RP.totals(day)
    assert t["business_minutes"] == 1.0 and t["paid_minutes"] == 1 and t["business_bp"] == 2500
    assert RP.totals([{"date": "x", "earned_micro": 0, "tokens": 0, "wh": 0.0, "minutes": 10, "paid_minutes": 3,
                       "cost_micro": 0}])["business_bp"] == 3000, "a row without business_minutes falls back to paid minutes"
