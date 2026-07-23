import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


def test_healthz_returns_200():
    client = APIClient()
    response = client.get("/healthz/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_can_create_a_user():
    User = get_user_model()
    user = User.objects.create_user(
        email="testuser@example.com", password="testpass123"
    )

    assert User.objects.count() == 1
    assert user.email == "testuser@example.com"
    assert user.is_active is False
    assert user.password != "testpass123"
    assert user.check_password("testpass123") is True
