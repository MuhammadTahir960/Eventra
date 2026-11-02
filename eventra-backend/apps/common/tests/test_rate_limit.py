import pytest

from apps.common.rate_limit import is_rate_limited

pytestmark = pytest.mark.django_db


def test_allows_requests_under_the_limit():
    for _ in range(3):
        assert is_rate_limited(key="test:under", limit=3, window_seconds=60) is False


def test_blocks_requests_once_the_limit_is_exceeded():
    for _ in range(3):
        is_rate_limited(key="test:over", limit=3, window_seconds=60)

    assert is_rate_limited(key="test:over", limit=3, window_seconds=60) is True


def test_different_keys_are_tracked_independently():
    for _ in range(3):
        is_rate_limited(key="test:key-a", limit=3, window_seconds=60)

    assert is_rate_limited(key="test:key-b", limit=3, window_seconds=60) is False


def test_a_rejected_attempt_still_counts_against_the_caller():
    for _ in range(5):
        is_rate_limited(key="test:retry", limit=1, window_seconds=60)

    assert is_rate_limited(key="test:retry", limit=1, window_seconds=60) is True
