import pytest
from datetime import timedelta
from django.core import mail
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from apps.common.constants import Roles
from ..models import User
from ..tokens import generate_password_reset_token, generate_verification_token
from ..factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def use_locmem_email_backend(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture
def api_client():
    return APIClient()


def auth_client(user):
    client = APIClient()
    access = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


# ==================================================
# POST /auth/register/
# ==================================================


class TestRegister:
    url = "/auth/register/"

    @pytest.mark.django_db(transaction=True)
    def test_valid_registration_creates_inactive_user_and_sends_email(self, api_client):
        payload = {
            "email": "newuser@example.com",
            "password": "a-genuinely-strong-pass-1",
            "first_name": "New",
            "last_name": "User",
        }
        response = api_client.post(self.url, payload)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "newuser@example.com"
        assert "password" not in response.data

        user = User.objects.get(email="newuser@example.com")
        assert user.is_active is False
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]

    def test_duplicate_email_rejected(self, api_client):
        UserFactory(email="taken@example.com")
        payload = {
            "email": "taken@example.com",
            "password": "a-genuinely-strong-pass-1",
            "first_name": "New",
            "last_name": "User",
        }
        response = api_client.post(self.url, payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_weak_password_rejected(self, api_client):
        payload = {
            "email": "newuser@example.com",
            "password": "12345",
            "first_name": "New",
            "last_name": "User",
        }
        response = api_client.post(self.url, payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert User.objects.filter(email="newuser@example.com").exists() is False

    def test_missing_fields_rejected(self, api_client):
        response = api_client.post(self.url, {"email": "incomplete@example.com"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db(transaction=True)
    def test_privileged_field_injection_is_ignored(self, api_client):
        payload = {
            "email": "attacker@example.com",
            "password": "a-genuinely-strong-pass-1",
            "first_name": "Att",
            "last_name": "Acker",
            "role": Roles.ADMIN,
            "is_staff": True,
            "is_superuser": True,
        }
        response = api_client.post(self.url, payload)
        assert response.status_code == status.HTTP_201_CREATED

        user = User.objects.get(email="attacker@example.com")
        assert user.role == Roles.ATTENDEE
        assert user.is_staff is False
        assert user.is_superuser is False

    def test_get_not_allowed(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_throttled_after_rate_exceeded(self, api_client):
        for i in range(5):
            api_client.post(
                self.url,
                {
                    "email": f"ratelimit{i}@example.com",
                    "password": "a-genuinely-strong-pass-1",
                    "first_name": "Rate",
                    "last_name": "Limit",
                },
            )
        response = api_client.post(
            self.url,
            {
                "email": "ratelimit-overflow@example.com",
                "password": "a-genuinely-strong-pass-1",
                "first_name": "Rate",
                "last_name": "Limit",
            },
        )
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


# ==================================================
# GET /auth/verify-email/
# ==================================================


class TestVerifyEmail:
    url = "/auth/verify-email/"

    def test_valid_token_activates_account(self, api_client):
        user = UserFactory(is_active=False, is_email_verified=False)
        token = generate_verification_token(user.id)

        response = api_client.get(self.url, {"token": token})

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.is_active is True
        assert user.is_email_verified is True

    def test_missing_token_returns_400(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_empty_token_string_returns_400(self, api_client):
        response = api_client.get(self.url, {"token": ""})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_token_returns_400(self, api_client):
        response = api_client.get(self.url, {"token": "garbage"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_already_verified_replay_still_returns_200(self, api_client):
        user = UserFactory(is_active=True, is_email_verified=True)
        token = generate_verification_token(user.id)

        response = api_client.get(self.url, {"token": token})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["detail"] == "Email already verified."

    def test_clicking_the_same_verification_link_twice_is_safe(self, api_client):
        user = UserFactory(is_active=False, is_email_verified=False)
        token = generate_verification_token(user.id)

        first = api_client.get(self.url, {"token": token})
        second = api_client.get(self.url, {"token": token})

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.is_active is True

    def test_throttled_after_rate_exceeded(self, api_client):
        for _ in range(20):
            api_client.get(self.url, {"token": "garbage"})
        response = api_client.get(self.url, {"token": "garbage"})
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


# ==================================================
# POST /auth/login/
# ==================================================


class TestLogin:
    url = "/auth/login/"

    def test_active_user_correct_credentials_returns_tokens(self, api_client):
        UserFactory(email="active@example.com", is_active=True)
        response = api_client.post(
            self.url, {"email": "active@example.com", "password": "testpass123"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data

    def test_inactive_user_rejected(self, api_client):
        UserFactory(email="unverified@example.com", is_active=False)
        response = api_client.post(
            self.url, {"email": "unverified@example.com", "password": "testpass123"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_wrong_password_rejected(self, api_client):
        UserFactory(email="active@example.com", is_active=True)
        response = api_client.post(
            self.url, {"email": "active@example.com", "password": "wrong-password"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_nonexistent_user_rejected(self, api_client):
        response = api_client.post(
            self.url, {"email": "nobody@example.com", "password": "whatever123"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_missing_credentials_rejected(self, api_client):
        response = api_client.post(self.url, {})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_email_case_insensitive(self, api_client):
        UserFactory(email="CaseSensitive@Example.com", is_active=True)
        response = api_client.post(
            self.url,
            {"email": "casesensitive@example.com", "password": "testpass123"},
        )
        assert response.status_code == status.HTTP_200_OK

    def test_throttled_after_rate_exceeded(self, api_client):
        for _ in range(10):
            api_client.post(
                self.url,
                {"email": "nobody@example.com", "password": "whatever123"},
            )
        response = api_client.post(
            self.url,
            {"email": "nobody@example.com", "password": "whatever123"},
        )
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


# ==================================================
# POST /auth/refresh/
# ==================================================


class TestRefresh:
    url = "/auth/refresh/"

    def test_valid_refresh_returns_new_access_token(self, api_client):
        user = UserFactory(is_active=True)
        refresh = RefreshToken.for_user(user)

        response = api_client.post(self.url, {"refresh": str(refresh)})

        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data

    def test_invalid_refresh_rejected(self, api_client):
        response = api_client.post(self.url, {"refresh": "not-a-real-token"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_original_refresh_token_cannot_be_reused_after_rotation(self, api_client):
        user = UserFactory(is_active=True)
        original_refresh = RefreshToken.for_user(user)

        first = api_client.post(self.url, {"refresh": str(original_refresh)})
        assert first.status_code == status.HTTP_200_OK
        assert "refresh" in first.data

        second = api_client.post(self.url, {"refresh": str(original_refresh)})
        assert second.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_not_allowed(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ==================================================
# POST /auth/logout/
# ==================================================


class TestLogout:
    url = "/auth/logout/"

    def test_logout_blacklists_refresh_token(self):
        user = UserFactory(is_active=True)
        refresh = RefreshToken.for_user(user)
        client = auth_client(user)

        response = client.post(self.url, {"refresh": str(refresh)})
        assert response.status_code == status.HTTP_205_RESET_CONTENT

        refresh_client = APIClient()
        replay = refresh_client.post("/auth/refresh/", {"refresh": str(refresh)})
        assert replay.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_requires_authentication(self, api_client):
        user = UserFactory(is_active=True)
        refresh = RefreshToken.for_user(user)
        response = api_client.post(self.url, {"refresh": str(refresh)})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_rejects_garbage_refresh_token(self):
        user = UserFactory(is_active=True)
        client = auth_client(user)
        response = client.post(self.url, {"refresh": "not-a-real-token"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "refresh" in response.data

    def test_logout_rejects_garbage_access_token(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-access-token")
        response = api_client.post(self.url, {"refresh": "irrelevant"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_rejects_another_users_refresh_token(self):
        victim = UserFactory(is_active=True)
        attacker = UserFactory(is_active=True)
        victims_refresh = RefreshToken.for_user(victim)
        client = auth_client(attacker)

        response = client.post(self.url, {"refresh": str(victims_refresh)})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "refresh" in response.data
        replay = APIClient().post("/auth/refresh/", {"refresh": str(victims_refresh)})
        assert replay.status_code == status.HTTP_200_OK

    def test_logout_rejects_already_blacklisted_token(self):
        user = UserFactory(is_active=True)
        refresh = RefreshToken.for_user(user)
        client = auth_client(user)

        first = client.post(self.url, {"refresh": str(refresh)})
        assert first.status_code == status.HTTP_205_RESET_CONTENT

        second = client.post(self.url, {"refresh": str(refresh)})
        assert second.status_code == status.HTTP_400_BAD_REQUEST
        assert "refresh" in second.data


# ==================================================
# GET/PATCH /auth/me/
# ==================================================


class TestMe:
    url = "/auth/me/"

    def test_requires_authentication(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_garbage_access_token_rejected(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-access-token")
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_expired_access_token_rejected(self, api_client):
        user = UserFactory(is_active=True)
        access = AccessToken.for_user(user)
        access.set_exp(lifetime=timedelta(seconds=-1))

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_delete_not_allowed(self):
        user = UserFactory()
        client = auth_client(user)
        response = client.delete(self.url)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_get_returns_own_profile(self):
        user = UserFactory(first_name="Ada", last_name="Lovelace")
        client = auth_client(user)
        response = client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == user.email
        assert response.data["first_name"] == "Ada"

    def test_patch_updates_own_name(self):
        user = UserFactory(first_name="Old")
        client = auth_client(user)
        response = client.patch(self.url, {"first_name": "New"})
        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.first_name == "New"

    def test_patch_cannot_change_email_or_role(self):
        user = UserFactory(email="original@example.com", role=Roles.ATTENDEE)
        client = auth_client(user)
        response = client.patch(
            self.url, {"email": "hacked@example.com", "role": Roles.ADMIN}
        )
        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.email == "original@example.com"
        assert user.role == Roles.ATTENDEE

    def test_cannot_see_or_edit_another_users_profile(self):
        UserFactory(email="victim@example.com", first_name="Victim")
        attacker = UserFactory(email="attacker@example.com", first_name="Attacker")
        client = auth_client(attacker)

        response = client.get(self.url)

        assert response.data["email"] == "attacker@example.com"
        assert response.data["email"] != "victim@example.com"


# ==================================================
# POST /auth/password-reset/, POST /auth/password-reset/confirm/
# ==================================================


class TestPasswordResetRequest:
    url = "/auth/password-reset/"

    def test_request_for_existing_user_sends_email_and_returns_200(self, api_client):
        user = UserFactory()
        response = api_client.post(self.url, {"email": user.email})
        assert response.status_code == status.HTTP_200_OK
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]

    def test_request_for_unknown_email_returns_same_200_and_sends_nothing(
        self, api_client
    ):
        response = api_client.post(self.url, {"email": "nobody@example.com"})
        assert response.status_code == status.HTTP_200_OK
        assert len(mail.outbox) == 0

    def test_response_body_identical_for_existing_and_unknown_email(self, api_client):
        user = UserFactory()
        known = api_client.post(self.url, {"email": user.email})
        unknown = api_client.post(self.url, {"email": "nobody@example.com"})
        assert known.data == unknown.data

    def test_invalid_email_format_returns_400(self, api_client):
        response = api_client.post(self.url, {"email": "not-an-email"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_email_returns_400(self, api_client):
        response = api_client.post(self.url, {})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_throttled_after_rate_exceeded(self, api_client):
        for _ in range(5):
            api_client.post(self.url, {"email": "nobody@example.com"})
        response = api_client.post(self.url, {"email": "nobody@example.com"})
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


class TestPasswordResetConfirm:
    url = "/auth/password-reset/confirm/"

    def test_valid_token_resets_password(self, api_client):
        user = UserFactory()
        user.set_password("original-strong-pass-1")
        user.save()
        token = generate_password_reset_token(user)

        response = api_client.post(
            self.url, {"token": token, "new_password": "a-new-strong-pass-2"}
        )

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.check_password("a-new-strong-pass-2")

    def test_reset_password_can_log_in_with_new_password(self, api_client):
        user = UserFactory(email="reset-me@example.com")
        token = generate_password_reset_token(user)
        api_client.post(
            self.url, {"token": token, "new_password": "a-new-strong-pass-2"}
        )

        login = APIClient().post(
            "/auth/login/",
            {"email": "reset-me@example.com", "password": "a-new-strong-pass-2"},
        )
        assert login.status_code == status.HTTP_200_OK

    def test_invalid_token_returns_400(self, api_client):
        response = api_client.post(
            self.url, {"token": "garbage", "new_password": "a-new-strong-pass-2"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_fields_returns_400(self, api_client):
        response = api_client.post(self.url, {})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_weak_password_rejected(self, api_client):
        user = UserFactory()
        token = generate_password_reset_token(user)
        response = api_client.post(self.url, {"token": token, "new_password": "123"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        user.refresh_from_db()
        assert not user.check_password("123")

    def test_token_cannot_be_reused(self, api_client):
        user = UserFactory()
        token = generate_password_reset_token(user)

        first = api_client.post(
            self.url, {"token": token, "new_password": "first-strong-pass-1"}
        )
        assert first.status_code == status.HTTP_200_OK

        second = api_client.post(
            self.url, {"token": token, "new_password": "second-strong-pass-2"}
        )
        assert second.status_code == status.HTTP_400_BAD_REQUEST

    def test_throttled_after_rate_exceeded(self, api_client):
        for _ in range(5):
            api_client.post(
                self.url, {"token": "garbage", "new_password": "a-strong-pass-1"}
            )
        response = api_client.post(
            self.url, {"token": "garbage", "new_password": "a-strong-pass-1"}
        )
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
