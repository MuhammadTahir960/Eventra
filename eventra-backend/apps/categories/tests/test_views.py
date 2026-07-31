import uuid
import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.common.constants import Roles
from apps.users.factories import UserFactory
from tests.helpers import results
from ..models import Category
from ..factories import CategoryFactory

pytestmark = pytest.mark.django_db


def auth_client(user):
    client = APIClient()
    access = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


@pytest.fixture
def admin():
    return UserFactory(role=Roles.ADMIN)


@pytest.fixture
def organizer():
    return UserFactory(role=Roles.ORGANIZER)


@pytest.fixture
def attendee():
    return UserFactory(role=Roles.ATTENDEE)


def _payload(**overrides):
    payload = {"name": "New Category", "icon": "star", "sort_order": 0}
    payload.update(overrides)
    return payload


# ==================================================
# GET /categories/ (list) & retrieve
# ==================================================


class TestListAndRetrieveCategory:
    def test_anonymous_can_list(self, api_client):
        CategoryFactory()
        response = api_client.get("/categories/")
        assert response.status_code == status.HTTP_200_OK

    def test_soft_deleted_categories_excluded_from_list(self, api_client):
        CategoryFactory(name="Visible")
        CategoryFactory(name="Hidden", is_active=False)
        response = api_client.get("/categories/")
        names = [c["name"] for c in results(response)]
        assert "Visible" in names
        assert "Hidden" not in names

    def test_anonymous_can_retrieve(self, api_client):
        category = CategoryFactory()
        response = api_client.get(f"/categories/{category.pk}/")
        assert response.status_code == status.HTTP_200_OK

    def test_retrieve_soft_deleted_returns_404(self, api_client):
        category = CategoryFactory(is_active=False)
        response = api_client.get(f"/categories/{category.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_nonexistent_returns_404(self, api_client):
        response = api_client.get(f"/categories/{uuid.uuid4()}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ==================================================
# POST /categories/ (create)
# ==================================================


class TestCreateCategory:
    url = "/categories/"

    def test_admin_can_create(self, admin):
        client = auth_client(admin)
        response = client.post(self.url, _payload())
        assert response.status_code == status.HTTP_201_CREATED
        assert Category.objects.filter(name="New Category").exists()

    def test_anonymous_cannot_create(self, api_client):
        response = api_client.post(self.url, _payload())
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_attendee_cannot_create(self, attendee):
        client = auth_client(attendee)
        response = client.post(self.url, _payload())
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_organizer_cannot_create(self, organizer):
        client = auth_client(organizer)
        response = client.post(self.url, _payload())
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_duplicate_name_rejected(self, admin):
        CategoryFactory(name="Music")
        client = auth_client(admin)
        response = client.post(self.url, _payload(name="Music"))
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_blank_name_rejected(self, admin):
        client = auth_client(admin)
        response = client.post(self.url, _payload(name=""))
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ==================================================
# PATCH /categories/{id}/ (update)
# ==================================================


class TestUpdateCategory:
    def test_admin_can_update(self, admin):
        category = CategoryFactory(name="Old Name")
        client = auth_client(admin)
        response = client.patch(f"/categories/{category.pk}/", {"name": "New Name"})
        assert response.status_code == status.HTTP_200_OK
        category.refresh_from_db()
        assert category.name == "New Name"

    def test_attendee_cannot_update(self, attendee):
        category = CategoryFactory(name="Old Name")
        client = auth_client(attendee)
        response = client.patch(f"/categories/{category.pk}/", {"name": "New Name"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_organizer_cannot_update(self, organizer):
        category = CategoryFactory(name="Old Name")
        client = auth_client(organizer)
        response = client.patch(f"/categories/{category.pk}/", {"name": "New Name"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_update(self, api_client):
        category = CategoryFactory(name="Old Name")
        response = api_client.patch(f"/categories/{category.pk}/", {"name": "New Name"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_into_duplicate_name_rejected(self, admin):
        CategoryFactory(name="Taken")
        category = CategoryFactory(name="Original")
        client = auth_client(admin)
        response = client.patch(f"/categories/{category.pk}/", {"name": "Taken"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ==================================================
# DELETE /categories/{id}/ (soft + hard delete)
# ==================================================


class TestDestroyCategory:
    def test_admin_soft_deletes_by_default(self, admin):
        category = CategoryFactory()
        client = auth_client(admin)
        response = client.delete(f"/categories/{category.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        category.refresh_from_db()
        assert category.is_active is False

    def test_admin_hard_deletes_with_query_param(self, admin):
        category = CategoryFactory()
        client = auth_client(admin)
        response = client.delete(f"/categories/{category.pk}/?hard=true")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert Category.all_objects.filter(pk=category.pk).exists() is False

    def test_soft_deleting_already_inactive_returns_404(self, admin):
        category = CategoryFactory(is_active=False)
        client = auth_client(admin)
        response = client.delete(f"/categories/{category.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_destroy_nonexistent_returns_404(self, admin):
        client = auth_client(admin)
        response = client.delete(f"/categories/{uuid.uuid4()}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_attendee_cannot_delete(self, attendee):
        category = CategoryFactory()
        client = auth_client(attendee)
        response = client.delete(f"/categories/{category.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_organizer_cannot_delete(self, organizer):
        category = CategoryFactory()
        client = auth_client(organizer)
        response = client.delete(f"/categories/{category.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_delete(self, api_client):
        category = CategoryFactory()
        response = api_client.delete(f"/categories/{category.pk}/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_attendee_cannot_hard_delete(self, attendee):
        category = CategoryFactory()
        client = auth_client(attendee)
        response = client.delete(f"/categories/{category.pk}/?hard=true")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert Category.all_objects.filter(pk=category.pk).exists()


# ==================================================
# POST /categories/{id}/restore/
# ==================================================


class TestRestoreCategory:
    def test_admin_can_restore(self, admin):
        category = CategoryFactory(is_active=False)
        client = auth_client(admin)
        response = client.post(f"/categories/{category.pk}/restore/")
        assert response.status_code == status.HTTP_200_OK
        category.refresh_from_db()
        assert category.is_active is True

    def test_attendee_cannot_restore(self, attendee):
        category = CategoryFactory(is_active=False)
        client = auth_client(attendee)
        response = client.post(f"/categories/{category.pk}/restore/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_organizer_cannot_restore(self, organizer):
        category = CategoryFactory(is_active=False)
        client = auth_client(organizer)
        response = client.post(f"/categories/{category.pk}/restore/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_restore(self, api_client):
        category = CategoryFactory(is_active=False)
        response = api_client.post(f"/categories/{category.pk}/restore/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_restoring_already_active_returns_409(self, admin):
        category = CategoryFactory(is_active=True)
        client = auth_client(admin)
        response = client.post(f"/categories/{category.pk}/restore/")
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_restoring_nonexistent_returns_404(self, admin):
        client = auth_client(admin)
        response = client.post(f"/categories/{uuid.uuid4()}/restore/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_restore_blocked_by_conflicting_active_category(self, admin):
        CategoryFactory(name="Music", is_active=True)
        deleted = CategoryFactory(name="Music", is_active=False)
        client = auth_client(admin)
        response = client.post(f"/categories/{deleted.pk}/restore/")
        assert response.status_code == status.HTTP_409_CONFLICT
        deleted.refresh_from_db()
        assert deleted.is_active is False
