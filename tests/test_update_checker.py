import pytest
from app.services.update_checker import parse_version_tuple, check_for_updates


def test_parse_version_tuple():
    assert parse_version_tuple("v1.0.24") == (1, 0, 24)
    assert parse_version_tuple("1.0.31") == (1, 0, 31)
    assert parse_version_tuple("v2.1.0-beta") == (2, 1, 0)
    assert parse_version_tuple("1.0.24") < parse_version_tuple("1.0.31")
    assert parse_version_tuple("1.1.0") > parse_version_tuple("1.0.99")


def test_check_for_updates_unauthenticated_or_valid():
    # Calling check_for_updates with mock or live:
    # If unauthenticated, it returns either an error or valid result, but must not crash
    res = check_for_updates(current_version="1.0.20")
    assert isinstance(res, dict)
    assert "has_update" in res
    assert "current_version" in res
    assert res["current_version"] == "1.0.20"
