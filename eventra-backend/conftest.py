import pytest
from django.core.cache import cache


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
