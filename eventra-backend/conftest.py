import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.users.factories import UserFactory


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """
    A test file that calls /auth/register/ more than 5 times in one run
    would start seeing real 429s unrelated to whatever it's actually
    testing. Clearing the cache before every test keeps each test's
    throttle budget isolated and the suite order-independent.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user():
    return UserFactory(role="admin", is_staff=True)


@pytest.fixture
def organizer_user():
    return UserFactory(role="organizer")


@pytest.fixture
def attendee_user():
    return UserFactory(role="attendee")


@pytest.fixture
def admin_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client
