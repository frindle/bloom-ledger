"""Once-a-day push with yesterday's Darkbloom earnings (Pushover). Stdlib only.

Sent once per UTC day, at or after DAILY_PUSH_HOUR (default 9, a UTC hour) so "yesterday" is Darkbloom's UTC day, when
PUSHOVER_TOKEN and PUSHOVER_USER are both set. The last sent day is kept in <data>/daily-push.json so a
restart never sends twice."""
import datetime as dt
import json
import urllib.parse
import urllib.request

PUSHOVER_URL = "https://api.pushover.net/1/messages.json"


def dollars(micro):
    return "unknown" if micro is None else f"${micro / 1_000_000:,.2f}"


def message(day, yesterday, month):
    """Title and body from two accounting summaries: `yesterday` (period day) and `month` (month to date)."""
    t, m = yesterday["totals"], month["totals"]
    when = dt.date.fromisoformat(day).strftime("%a %b %-d")
    lines = [f"Earned {dollars(t['earned_micro'])} over {t['paid_hours']:g} paid hours"]
    if t.get("cost_micro") is not None:
        lines.append(f"Power {dollars(t['cost_micro'])} ({t['kwh']:g} kWh)")
    lines.append(f"{dt.date.fromisoformat(day):%B} so far: {dollars(m['earned_micro'])} earned")
    return f"Darkbloom {when}", "\n".join(lines)


def due(state, now_utc, hour):
    """The UTC day to report (yesterday), or None when it was already sent or it is before `hour` (a UTC hour).

    `now_utc` must already be in UTC; this function does no zone conversion."""
    if now_utc.hour < hour:
        return None
    day = (now_utc.date() - dt.timedelta(days=1)).isoformat()
    return None if state.get("last_sent") == day else day


def send(token, user, title, body, opener=urllib.request.urlopen):
    data = urllib.parse.urlencode({"token": token, "user": user, "title": title, "message": body}).encode()
    opener(urllib.request.Request(PUSHOVER_URL, data=data, method="POST"), timeout=15).close()


def run(path, now_utc, hour, build, token, user, opener=urllib.request.urlopen):
    """Send yesterday's push if due. `build(today, period)` returns an accounting summary. Returns the day sent or None."""
    if not (token and user):
        return None
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        state = {}
    day = due(state, now_utc, hour)
    if day is None:
        return None
    title, body = message(day, build(day, "day"), build(day, "month"))
    send(token, user, title, body, opener)
    path.write_text(json.dumps({"last_sent": day}))
    return day
