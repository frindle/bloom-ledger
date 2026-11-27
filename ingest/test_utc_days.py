"""Days, months and 'today' are UTC (Darkbloom's accounting day); electricity prices are read on the local wall clock
(settings local_timezone). Each test would fail if the two zones were swapped. Fake numbers."""
import datetime as dt
import sqlite3

import bloom_accounting_config as CF
import bloom_accounting_index as AX
import bloom_accounting_report as RP
import bloom_accounting_summary as SM
import bloom_accounting_tally as TL
import bloom_daily_push as DP
import bloom_earnings_series as ES
import server as SV

LA = "America/Los_Angeles"
OFF, PEAK = "0.10", "0.50"
# Peak 17:00-21:00 local. No adder, charge or fee, so 1000 Wh costs exactly the rate (rate * 1e6 micro-USD).
PEAK_SCHED = [{"months": list(range(1, 13)), "periods": [
    {"start": "00:00", "end": "17:00", "rate": OFF}, {"start": "17:00", "end": "21:00", "rate": PEAK}, {"start": "21:00", "end": "24:00", "rate": OFF}]}]
# One rate per month, to see which month's season a minute near a month edge gets.
SEASONS = [{"months": [11], "periods": [{"start": "00:00", "end": "24:00", "rate": "0.20"}]},
           {"months": [12], "periods": [{"start": "00:00", "end": "24:00", "rate": "0.30"}]}]
# 01:00-02:00 local is dear: on the fall-back day that wall hour happens twice.
DST_SCHED = [{"months": list(range(1, 13)), "periods": [
    {"start": "00:00", "end": "01:00", "rate": OFF}, {"start": "01:00", "end": "02:00", "rate": PEAK}, {"start": "02:00", "end": "24:00", "rate": OFF}]}]


def utc(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


def prices(schedule):
    return {"rate_schedule": schedule, "rate_adder_usd_per_kwh": 0, "universal_charge_usd_per_kwh": 0, "county_fee_pct": 0,
            "local_timezone": LA}


def make(earn=(), power=(), schedule=None):
    """earn: (ts, micro_usd); power: (ts, wh). The schedule and local_timezone=LA are stored as settings."""
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    for i, (ts, micro) in enumerate(earn):
        db.execute("INSERT INTO earnings VALUES (?, ?, ?, 'job', 'm', ?, 1, 'm4')", ("e%d" % i, ts, micro, "j%d" % i))
    for ts, wh in power:
        db.execute("INSERT INTO power_minutes (machine_id, ts, wh, interval_s, power_ok, other_work, tokens_delta) VALUES ('m4',?,?,60,1,0,0)", (ts, wh))
    db.commit()
    for k, v in prices(schedule or PEAK_SCHED).items():   # the LA zone must not move any day boundary
        CF.set_setting(db, k, v, "1970-01-01", 1)
    return db


def costs_by_day(db, start, end, schedule):
    return {r["date"]: r["cost_micro"] for r in RP.day_rows(db, CF.ACCOUNTING_TZ, start, end, None, prices(schedule))}


def test_accounting_zone_is_utc(monkeypatch):
    assert CF.ACCOUNTING_TZ == "UTC"
    monkeypatch.setattr(CF, "utc_now", lambda: dt.datetime(2026, 11, 5, 23, 59, 59, tzinfo=dt.timezone.utc))
    assert CF.utc_today() == "2026-11-05"
    monkeypatch.setattr(CF, "utc_now", lambda: dt.datetime(2026, 11, 6, 0, 0, 0, tzinfo=dt.timezone.utc))
    assert CF.utc_today() == "2026-11-06"   # the clock is patched, so this cannot flake at midnight


def test_day_boundary_is_midnight_utc_not_local_midnight():
    # 06:59Z Nov 2 is still Nov 1 in Los Angeles but Nov 2 in UTC.
    db = make(earn=[(utc(2026, 11, 1, 23, 59, 59), 1), (utc(2026, 11, 2, 0, 0, 0), 10), (utc(2026, 11, 2, 6, 59, 0), 100)])
    assert SM.build(db, "2026-11-02", "day")["totals"]["earned_micro"] == 110
    assert SM.build(db, "2026-11-01", "day")["totals"]["earned_micro"] == 1
    assert SM.build(db, "2026-11-30", "month")["totals"]["earned_micro"] == 111


def test_peak_hour_is_chosen_from_local_time_but_filed_on_the_utc_day():
    # 02:00Z Jul 16 is 19:00 on Jul 15 in Los Angeles: a peak minute, filed on UTC day Jul 16.
    # 18:00Z Jul 15 is 11:00 locally (off-peak) although 18:00 is inside the peak window when read as UTC.
    db = make(power=[(utc(2026, 7, 16, 2, 0), 1000.0), (utc(2026, 7, 15, 18, 0), 1000.0)])
    assert costs_by_day(db, "2026-07-15", "2026-07-16", PEAK_SCHED) == {"2026-07-15": 100000, "2026-07-16": 500000}
    # Through a real call site that reads the stored settings.
    assert SM.build(db, "2026-07-16", "day")["totals"]["cost_micro"] == 500000
    assert SM.build(db, "2026-07-15", "day")["totals"]["cost_micro"] == 100000


def test_day_detail_hours_are_utc_and_costs_use_local_prices():
    db = make(power=[(utc(2026, 7, 16, 2, 0), 1000.0)])
    d = RP.day_detail(db, CF.ACCOUNTING_TZ, "2026-07-16", None, prices(PEAK_SCHED))
    assert [(m["time"], m["cost_micro"]) for m in d["minutes"]] == [("02:00", 500000)]
    assert [(h["hour"], h["cost_micro"]) for h in d["hours"]] == [(2, 500000)]
    assert RP.day_detail(db, CF.ACCOUNTING_TZ, "2026-07-15", None, prices(PEAK_SCHED))["minutes"] == []


def test_rate_zone_comes_from_settings_and_defaults_to_utc():
    assert RP.rate_zone({"local_timezone": LA}) == LA
    assert RP.rate_zone({}) == "UTC" and RP.rate_zone(None) == "UTC"


def test_month_boundary_is_midnight_utc_while_the_season_follows_local_time():
    # 00:00Z Dec 1 is 16:00 on Nov 30 in Los Angeles: it is December's data, priced with November's season.
    # 08:00Z Dec 1 is local midnight, December in both zones.
    db = make(power=[(utc(2026, 11, 30, 23, 59), 10000.0), (utc(2026, 12, 1, 0, 0), 10000.0), (utc(2026, 12, 1, 8, 0), 10000.0)],
              schedule=SEASONS)
    assert SM.build(db, "2026-11-15", "month")["totals"]["cost_micro"] == 2000000
    assert SM.build(db, "2026-12-15", "month")["totals"]["cost_micro"] == 2000000 + 3000000
    assert TL.months_with_data(db) == ["2026-11", "2026-12"]


def test_tally_month_holds_the_first_utc_instant_of_the_month():
    db = make(earn=[(utc(2026, 11, 30, 23, 59, 59), 3000000), (utc(2026, 12, 1, 0, 0, 0), 5000000)])
    now = utc(2027, 1, 1)
    assert TL.build_month(db, "2026-11", now)["totals"]["earnings_cents"] == 300
    assert TL.build_month(db, "2026-12", now)["totals"]["earnings_cents"] == 500


def test_fall_back_day_is_one_24h_utc_day_and_the_repeated_local_hour_is_priced_twice():
    # 2026-11-01 in Los Angeles: clocks go back at 09:00Z, so local 01:30 happens at 08:30Z (PDT) and 09:30Z (PST).
    db = make(power=[(utc(2026, 11, 1, 7, 59), 1000.0), (utc(2026, 11, 1, 8, 30), 1000.0),
                     (utc(2026, 11, 1, 9, 30), 1000.0), (utc(2026, 11, 1, 10, 30), 1000.0)])
    assert costs_by_day(db, "2026-11-01", "2026-11-01", DST_SCHED) == {"2026-11-01": 100000 + 500000 + 500000 + 100000}
    assert RP.ts_bounds(CF.ACCOUNTING_TZ, "2026-11-01", "2026-11-01") == (utc(2026, 11, 1), utc(2026, 11, 2))   # 24h; LA's day is 25h
    assert RP.ts_bounds(CF.ACCOUNTING_TZ, "2026-03-08", "2026-03-08") == (utc(2026, 3, 8), utc(2026, 3, 9))     # spring-forward day too


def test_spring_forward_does_not_move_the_utc_day():
    # 2026-03-08: at 10:00Z local time jumps from 02:00 PST to 03:00 PDT, so 10:00Z is the first minute of the dear period.
    sched = [{"months": list(range(1, 13)), "periods": [{"start": "00:00", "end": "03:00", "rate": OFF}, {"start": "03:00", "end": "24:00", "rate": PEAK}]}]
    db = make(power=[(utc(2026, 3, 8, 9, 59), 1000.0), (utc(2026, 3, 8, 10, 0), 1000.0)], schedule=sched)
    assert costs_by_day(db, "2026-03-08", "2026-03-08", sched) == {"2026-03-08": 100000 + 500000}


def test_settings_rows_are_looked_up_by_calendar_day_across_a_month_edge():
    # A row dated by a calendar day applies from that day (compared as text, no zone): the month that ends the day before does not see it.
    db = sqlite3.connect(":memory:")
    CF.set_setting(db, "local_timezone", "UTC", "1970-01-01", 1)
    CF.set_setting(db, "local_timezone", LA, "2026-12-01", 2)
    assert CF.effective_settings(db, "2026-11-30")["values"]["local_timezone"] == "UTC"
    assert CF.effective_settings(db, "2026-12-01")["values"]["local_timezone"] == LA


def test_earnings_series_today_is_the_utc_day(monkeypatch):
    # 01:00Z Nov 5 is still Nov 4 in Los Angeles; the chart's open day must be the UTC one.
    monkeypatch.setenv("BLOOM_TIMEZONE", LA)
    monkeypatch.setattr(CF, "utc_now", lambda: dt.datetime(2026, 11, 5, 1, 0, tzinfo=dt.timezone.utc))
    db = make(earn=[(utc(2026, 11, 4, 12, 0), 9)])
    assert [d["date"] for d in ES.build(db)["days"]] == ["2026-11-04", "2026-11-05"]


def push_setup(monkeypatch, tmp_path, now, hour):
    sent = []
    monkeypatch.setattr(CF, "utc_now", lambda: now)
    monkeypatch.setattr(SV, "ROOT", tmp_path)
    monkeypatch.setattr(SV, "PUSHOVER_TOKEN", "t")
    monkeypatch.setattr(SV, "PUSHOVER_USER", "u")
    monkeypatch.setattr(SV, "DAILY_PUSH_HOUR", hour)
    monkeypatch.setattr(DP, "send", lambda token, user, title, body, opener=None: sent.append(title))
    return sent


def test_scheduler_push_hour_is_a_utc_hour(monkeypatch, tmp_path):
    db = make()
    # 08:59Z is 00:59 in Los Angeles and 09:00Z is 01:00 there: only a UTC clock makes hour 9 due at 09:00Z.
    sent = push_setup(monkeypatch, tmp_path, dt.datetime(2026, 11, 5, 8, 59, tzinfo=dt.timezone.utc), 9)
    assert SV.daily_push_tick(db) is None and sent == []
    monkeypatch.setattr(CF, "utc_now", lambda: dt.datetime(2026, 11, 5, 9, 0, tzinfo=dt.timezone.utc))
    assert SV.daily_push_tick(db) == "2026-11-04" and len(sent) == 1
    assert SV.daily_push_tick(db) is None and len(sent) == 1   # once per day


def test_scheduler_reports_the_previous_utc_day_not_the_local_one(monkeypatch, tmp_path):
    db = make()
    # 03:00Z Nov 5 is still the evening of Nov 4 in Los Angeles; a local clock would report Nov 3.
    sent = push_setup(monkeypatch, tmp_path, dt.datetime(2026, 11, 5, 3, 0, tzinfo=dt.timezone.utc), 0)
    assert SV.daily_push_tick(db) == "2026-11-04" and len(sent) == 1
