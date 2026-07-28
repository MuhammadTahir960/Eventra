from rest_framework.test import APIClient


def test_healthz_returns_200():
    client = APIClient()
    response = client.get("/healthz/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_post_not_allowed():
    client = APIClient()
    response = client.post("/healthz/")
    assert response.status_code == 405
