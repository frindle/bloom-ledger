"""Frozen test: settings.html relative times use the right ranges, and an HTTP error is reported."""
import copy

import dom_support as D

BASE = {"generated_at": 1793300000, "admin_enabled": True,
        "machines": [{"id": "a", "last_seen": 1793300000 - 1800, "objects": 1, "days_sealed": 0, "status": "reporting"},
                     {"id": "b", "last_seen": 1793300000 - 3 * 3600, "objects": 1, "days_sealed": 0, "status": "silent"},
                     {"id": "c", "last_seen": 1793300000 - 3 * 86400, "objects": 1, "days_sealed": 0, "status": "silent"}],
        "health": {"version": "v", "time": 1793300000, "data_bytes": 10, "objects": 3}}


def test_relative_time_ranges(tmp_path):
    res = D.run_page(tmp_path, {"/v1/settings": {"status": 200, "body": copy.deepcopy(BASE)}})
    assert [r[1] for r in D.rows(res)] == ["30 minutes ago", "3 hours ago", "3 days ago"], D.rows(res)


def test_http_error_is_reported_as_unreachable(tmp_path):
    res = D.run_page(tmp_path, {"/v1/settings": {"status": 500, "body": {"error": "boom"}}})
    note = D.find(res["dom"], "admin-note")
    assert "Can't reach the ledger" in note["text"] and note["hidden"] is False
    assert D.rows(res) == []
