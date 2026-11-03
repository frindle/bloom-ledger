import json
import sqlite3

import bloom_accounting_index as AX
import bloom_accounting_report as RP
from server_fixture import web  # noqa: F401

T0 = 1793664000  # 2026-11-03T00:00:00Z


def _db():
    db = sqlite3.connect(":memory:")
    AX.create_schema(db)
    rows = [(T0, 0, 1, 0), (T0 + 60, 50, 0, 0), (T0 + 120, 0, 0, 1), (T0 + 180, 0, 0, 0)]  # (ts, tokens, sbx, other)
    for ts, tok, sbx, other in rows:
        db.execute("INSERT INTO power_minutes VALUES ('m', ?, 2.0, 60, 1, 'serving', ?, ?, ?)", (ts, other, tok, sbx))
    db.execute("INSERT INTO power_minutes VALUES ('m', ?, 0, 60, 0, '', 0, 0, 0)", (T0 + 240,))
    for lid, ts, micro, kind, model in (("a", T0 + 5, 1000, "sandbox", "sandbox:linux"), ("b", T0 + 65, 300, "job", "gemma"),
                                        ("c", T0 + 3700, 200, "base", "base_reward")):
        db.execute("INSERT INTO earnings VALUES (?, ?, ?, ?, ?, ?, ?, 'm')", (lid, ts, micro, kind, model, "j-" + lid, 7))
    return db


def test_day_rows_split_streams():
    r = RP.day_rows(_db(), "UTC", "2026-11-03", "2026-11-03", settings=None)[0]
    assert (r["gpu_micro"], r["sandbox_micro"], r["earned_micro"]) == (500, 1000, 1500)
    assert (r["gpu_minutes"], r["sandbox_minutes"], r["other_minutes"], r["paid_minutes"], r["minutes"]) == (1, 1, 1, 2, 4)


def test_day_detail_lists_every_entry_and_minute():
    d = RP.day_detail(_db(), "UTC", "2026-11-03")
    assert [(e["time"], e["stream"], e["model"]) for e in d["earnings"]] == [
        ("00:00:05", "sandbox", "sandbox:linux"), ("00:01:05", "gpu", "gemma"), ("01:01:40", "gpu", "base_reward")]
    assert [(m["time"], m["stream"]) for m in d["minutes"]] == [
        ("00:00", "sandbox"), ("00:01", "gpu"), ("00:02", "other"), ("00:03", "idle"), ("00:04", "gap")]
    h0 = d["hours"][0]
    assert (h0["hour"], h0["sandbox"], h0["gpu"], h0["other"], h0["idle"], h0["gap"], h0["wh"]) == (0, 1, 1, 1, 1, 1, 8.0)
    assert (h0["gpu_micro"], h0["sandbox_micro"]) == (300, 1000) and d["hours"][1]["gpu_micro"] == 200


def test_day_detail_respects_local_timezone():
    d = RP.day_detail(_db(), "America/Los_Angeles", "2026-11-02")
    assert d["earnings"][0]["time"] == "16:00:05" and len(d["minutes"]) == 5


def test_day_route(web):
    status, ctype, body = web("GET", "/v1/accounting/day?date=2026-11-03")
    assert status == 200 and ctype.startswith("application/json")
    assert json.loads(body)["date"] == "2026-11-03" and json.loads(body)["earnings"] == []
    assert web("GET", "/v1/accounting/day?date=nope")[0] == 400
