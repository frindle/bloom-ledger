import datetime as dt
import json
import urllib.parse

import bloom_daily_push as DP


def summ(earned, hours=2.5, cost=400_000, kwh=1.2):
    return {"totals": {"earned_micro": earned, "paid_hours": hours, "cost_micro": cost, "kwh": kwh}}


def test_message_text():
    title, body = DP.message("2026-11-04", summ(1_234_567), summ(12_300_000))
    assert title == "Darkbloom Wed Nov 4"
    assert body.splitlines() == ["Earned $1.23 over 2.5 paid hours", "Power $0.40 (1.2 kWh)", "November so far: $12.30 earned"]


def test_message_without_power_cost():
    _, body = DP.message("2026-11-04", summ(0, cost=None), summ(0))
    assert "Power" not in body


def test_due_waits_for_hour_and_sends_once():
    morning = dt.datetime(2026, 11, 5, 8, 59)
    nine = dt.datetime(2026, 11, 5, 9, 0)
    assert DP.due({}, morning, 9) is None
    assert DP.due({}, nine, 9) == "2026-11-04"
    assert DP.due({"last_sent": "2026-11-04"}, nine, 9) is None
    assert DP.due({"last_sent": "2026-11-03"}, nine, 9) == "2026-11-04"


def test_run_sends_once_and_records(tmp_path):
    sent = []
    built = []

    class Resp:
        def close(self):
            pass

    def opener(req, timeout):
        sent.append(urllib.parse.parse_qs(req.data.decode()))
        return Resp()

    def build(day, period):
        built.append((day, period))
        return summ(1_000_000)

    path = tmp_path / "daily-push.json"
    now = dt.datetime(2026, 11, 5, 10, 0)
    assert DP.run(path, now, 9, build, "tok", "usr", opener) == "2026-11-04"
    assert built == [("2026-11-04", "day"), ("2026-11-04", "month")]
    assert sent[0]["token"] == ["tok"] and sent[0]["user"] == ["usr"] and sent[0]["title"] == ["Darkbloom Wed Nov 4"]
    assert json.loads(path.read_text()) == {"last_sent": "2026-11-04"}
    assert DP.run(path, now, 9, build, "tok", "usr", opener) is None
    assert len(sent) == 1


def test_run_needs_both_credentials(tmp_path):
    def boom(*a, **k):
        raise AssertionError("must not send")
    assert DP.run(tmp_path / "p.json", dt.datetime(2026, 11, 5, 10), 9, boom, "", "usr", boom) is None
    assert DP.run(tmp_path / "p.json", dt.datetime(2026, 11, 5, 10), 9, boom, "tok", "", boom) is None


def test_failed_send_does_not_record(tmp_path):
    def opener(req, timeout):
        raise OSError("down")
    path = tmp_path / "p.json"
    try:
        DP.run(path, dt.datetime(2026, 11, 5, 10), 9, lambda d, p: summ(1), "tok", "usr", opener)
    except OSError:
        pass
    assert not path.exists()
