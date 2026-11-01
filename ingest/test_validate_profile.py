"""Frozen test: bloom_machine_profiles.validate_profile (synthetic values only)."""
import pytest

import bloom_machine_profiles as MP


def test_validate_accepts_empty_full_and_null_values():
    assert MP.validate_profile({}) == {}
    assert MP.validate_profile({"display_name": "Desk", "model": "Test-Model 1", "lease_start": "2026-01-31",
                                "lease_monthly_cents": 100}) == {}
    assert MP.validate_profile({"display_name": None, "model": None, "lease_start": None, "lease_monthly_cents": None}) == {}
    assert MP.validate_profile({"display_name": "x" * 60}) == {}


@pytest.mark.parametrize("fields,key", [
    ({"display_name": "   "}, "display_name"),
    ({"display_name": "x" * 61}, "display_name"),
    ({"display_name": 5}, "display_name"),
    ({"model": ""}, "model"),
    ({"model": "y" * 61}, "model"),
    ({"lease_start": "2026-02-30"}, "lease_start"),
    ({"lease_start": "26-1-1"}, "lease_start"),
    ({"lease_start": 20260101}, "lease_start"),
    ({"lease_monthly_cents": 0}, "lease_monthly_cents"),
    ({"lease_monthly_cents": -5}, "lease_monthly_cents"),
    ({"lease_monthly_cents": True}, "lease_monthly_cents"),
    ({"lease_monthly_cents": 1.5}, "lease_monthly_cents"),
    ({"lease_monthly_cents": "100"}, "lease_monthly_cents"),
    ({"admin": "x"}, "admin"),
])
def test_validate_rejects_bad_values(fields, key):
    assert key in MP.validate_profile(fields)


def test_validate_reports_every_bad_key_and_rejects_non_objects():
    errs = MP.validate_profile({"model": "", "lease_monthly_cents": 0})
    assert sorted(errs) == ["lease_monthly_cents", "model"]
    assert MP.validate_profile([1]) == {"form": "not an object"}
    assert MP.validate_profile(None) == {"form": "not an object"}
