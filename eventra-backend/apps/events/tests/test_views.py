import io
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.categories.factories import CategoryFactory
from apps.common.constants import Roles
from apps.sports.factories import SportFactory, TeamFactory
from apps.users.factories import UserFactory
from apps.venues.factories import VenueFactory
from tests.helpers import results

from ..factories import EventFactory, TicketTierFactory, TierSectionMappingFactory
from ..models import Event, TicketTier, TierSectionMapping
from ..services import TierPriceImmutableError

pytestmark = pytest.mark.django_db


def auth_client(user):
    client = APIClient()
    access = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _event_payload(**overrides):
    start = timezone.now() + timedelta(days=10)
    payload = {
        "venue": str(VenueFactory().id),
        "category": str(CategoryFactory().id),
        "title": "New Event",
        "description": "Details here.",
        "event_type": Event.EventType.GENERAL,
        "is_seated": True,
        "start_datetime": start.isoformat(),
        "end_datetime": (start + timedelta(hours=3)).isoformat(),
    }
    payload.update(overrides)
    return payload


# ==================================================
# GET /events/ (list) — visibility rules
# ==================================================


class TestListEvents:
    url = "/events/"

    def test_anonymous_sees_only_approved_and_completed(self, api_client):
        EventFactory(status=Event.Status.APPROVED, title="Approved")
        EventFactory(status=Event.Status.COMPLETED, title="Completed")
        EventFactory(status=Event.Status.PENDING_APPROVAL, title="Pending")
        EventFactory(status=Event.Status.REJECTED, title="Rejected")
        EventFactory(status=Event.Status.CANCELLED, title="Cancelled")

        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        titles = {e["title"] for e in results(response)}
        assert titles == {"Approved", "Completed"}

    def test_attendee_sees_only_approved_and_completed(self, attendee_user):
        EventFactory(status=Event.Status.APPROVED, title="Approved")
        EventFactory(status=Event.Status.PENDING_APPROVAL, title="Pending")

        client = auth_client(attendee_user)
        response = client.get(self.url)
        titles = {e["title"] for e in results(response)}
        assert titles == {"Approved"}

    def test_organizer_sees_own_events_at_any_status(self, organizer_user):
        EventFactory(
            organizer=organizer_user,
            status=Event.Status.PENDING_APPROVAL,
            title="Mine Pending",
        )
        EventFactory(
            organizer=organizer_user,
            status=Event.Status.REJECTED,
            title="Mine Rejected",
        )

        client = auth_client(organizer_user)
        response = client.get(self.url)
        titles = {e["title"] for e in results(response)}
        assert titles == {"Mine Pending", "Mine Rejected"}

    def test_organizer_does_not_see_other_organizers_pending_event(
        self, organizer_user
    ):
        other = UserFactory(role=Roles.ORGANIZER)
        EventFactory(
            organizer=other, status=Event.Status.PENDING_APPROVAL, title="Not Mine"
        )

        client = auth_client(organizer_user)
        response = client.get(self.url)
        titles = {e["title"] for e in results(response)}
        assert "Not Mine" not in titles

    def test_organizer_sees_other_organizers_approved_event(self, organizer_user):
        other = UserFactory(role=Roles.ORGANIZER)
        EventFactory(
            organizer=other, status=Event.Status.APPROVED, title="Other Approved"
        )

        client = auth_client(organizer_user)
        response = client.get(self.url)
        titles = {e["title"] for e in results(response)}
        assert "Other Approved" in titles

    def test_admin_sees_everything(self, admin_client):
        EventFactory(status=Event.Status.PENDING_APPROVAL, title="Pending")
        EventFactory(status=Event.Status.REJECTED, title="Rejected")
        EventFactory(status=Event.Status.CANCELLED, title="Cancelled")

        response = admin_client.get(self.url)
        titles = {e["title"] for e in results(response)}
        assert {"Pending", "Rejected", "Cancelled"} <= titles

    def test_soft_deleted_event_excluded_for_everyone(self, admin_client):
        event = EventFactory(status=Event.Status.APPROVED, title="Gone")
        event.is_active = False
        event.save(update_fields=["is_active"])

        response = admin_client.get(self.url)
        titles = {e["title"] for e in results(response)}
        assert "Gone" not in titles

    # ---- filters ----

    def test_filter_by_event_type(self, api_client):
        EventFactory(
            status=Event.Status.APPROVED,
            event_type=Event.EventType.GENERAL,
            title="General",
        )
        EventFactory(
            status=Event.Status.APPROVED,
            event_type=Event.EventType.SPORTS_MATCH,
            title="Match",
        )
        response = api_client.get(
            self.url, {"event_type": Event.EventType.SPORTS_MATCH}
        )
        titles = {e["title"] for e in results(response)}
        assert titles == {"Match"}

    def test_filter_by_status(self, admin_client):
        EventFactory(status=Event.Status.APPROVED, title="Approved")
        EventFactory(status=Event.Status.REJECTED, title="Rejected")
        EventFactory(status=Event.Status.CANCELLED, title="Cancelled")

        response = admin_client.get(self.url, {"status": Event.Status.REJECTED})
        titles = {e["title"] for e in results(response)}
        assert titles == {"Rejected"}

    def test_status_filter_composes_with_visibility_not_bypass_it(self, api_client):
        EventFactory(status=Event.Status.PENDING_APPROVAL, title="Hidden Pending")

        response = api_client.get(self.url, {"status": Event.Status.PENDING_APPROVAL})
        assert response.status_code == status.HTTP_200_OK
        titles = {e["title"] for e in results(response)}
        assert titles == set()

    def test_filter_by_category(self, api_client):
        target_category = CategoryFactory()
        EventFactory(
            status=Event.Status.APPROVED, category=target_category, title="Target"
        )
        EventFactory(status=Event.Status.APPROVED, title="Other")
        response = api_client.get(self.url, {"category": str(target_category.id)})
        titles = {e["title"] for e in results(response)}
        assert titles == {"Target"}

    def test_filter_by_city_case_insensitive(self, api_client):
        venue = VenueFactory(city="Nairobi")
        EventFactory(status=Event.Status.APPROVED, venue=venue, title="Nairobi Event")
        EventFactory(
            status=Event.Status.APPROVED,
            venue=VenueFactory(city="Mombasa"),
            title="Mombasa Event",
        )
        response = api_client.get(self.url, {"city": "NAIROBI"})
        titles = {e["title"] for e in results(response)}
        assert titles == {"Nairobi Event"}

    def test_filter_by_date_range(self, api_client):
        near = timezone.now() + timedelta(days=1)
        far = timezone.now() + timedelta(days=100)
        EventFactory(
            status=Event.Status.APPROVED,
            start_datetime=near,
            end_datetime=near + timedelta(hours=2),
            title="Near",
        )
        EventFactory(
            status=Event.Status.APPROVED,
            start_datetime=far,
            end_datetime=far + timedelta(hours=2),
            title="Far",
        )

        response = api_client.get(
            self.url,
            {
                "date_from": near.date().isoformat(),
                "date_to": (near + timedelta(days=5)).date().isoformat(),
            },
        )
        titles = {e["title"] for e in results(response)}
        assert titles == {"Near"}

    def test_filter_by_min_max_price(self, api_client):
        cheap = EventFactory(status=Event.Status.APPROVED, title="Cheap")
        TicketTierFactory(event=cheap, price="10.00")
        pricey = EventFactory(status=Event.Status.APPROVED, title="Pricey")
        TicketTierFactory(event=pricey, price="500.00")

        response = api_client.get(self.url, {"min_price": "100"})
        titles = {e["title"] for e in results(response)}
        assert titles == {"Pricey"}

        response = api_client.get(self.url, {"max_price": "100"})
        titles = {e["title"] for e in results(response)}
        assert titles == {"Cheap"}

    def test_filter_by_search_matches_title_and_description(self, api_client):
        EventFactory(
            status=Event.Status.APPROVED,
            title="Jazz Night",
            description="An evening of jazz.",
        )
        EventFactory(
            status=Event.Status.APPROVED,
            title="Football Final",
            description="The big match.",
        )

        response = api_client.get(self.url, {"search": "jazz"})
        titles = {e["title"] for e in results(response)}
        assert titles == {"Jazz Night"}


# ==================================================
# GET /events/{id}/ (retrieve)
# ==================================================


class TestRetrieveEvent:
    def test_anonymous_can_retrieve_approved_event(self, api_client):
        event = EventFactory(status=Event.Status.APPROVED)
        response = api_client.get(f"/events/{event.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(event.pk)

    def test_anonymous_cannot_retrieve_pending_event(self, api_client):
        event = EventFactory(status=Event.Status.PENDING_APPROVAL)
        response = api_client.get(f"/events/{event.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_organizer_can_retrieve_own_pending_event(self, organizer_user):
        event = EventFactory(
            organizer=organizer_user, status=Event.Status.PENDING_APPROVAL
        )
        client = auth_client(organizer_user)
        response = client.get(f"/events/{event.pk}/")
        assert response.status_code == status.HTTP_200_OK

    def test_organizer_cannot_retrieve_other_organizers_pending_event(
        self, organizer_user
    ):
        other = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(organizer=other, status=Event.Status.PENDING_APPROVAL)
        client = auth_client(organizer_user)
        response = client.get(f"/events/{event.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_soft_deleted_event_returns_404(self, admin_client):
        event = EventFactory(status=Event.Status.APPROVED)
        event.is_active = False
        event.save(update_fields=["is_active"])
        response = admin_client.get(f"/events/{event.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ==================================================
# POST /events/ (create)
# ==================================================


class TestCreateEvent:
    url = "/events/"

    def test_organizer_create_lands_pending_approval(self, organizer_user):
        client = auth_client(organizer_user)
        response = client.post(self.url, _event_payload(), format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["status"] == Event.Status.PENDING_APPROVAL
        assert str(response.data["organizer"]) == str(organizer_user.id)

    def test_admin_create_lands_approved(self, admin_user):
        client = auth_client(admin_user)
        response = client.post(self.url, _event_payload(), format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["status"] == Event.Status.APPROVED

    def test_attendee_cannot_create(self, attendee_user):
        client = auth_client(attendee_user)
        response = client.post(self.url, _event_payload(), format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_create(self, api_client):
        response = api_client.post(self.url, _event_payload(), format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_payload_rejected(self, organizer_user):
        client = auth_client(organizer_user)
        response = client.post(self.url, {"title": "Only A Title"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_end_before_start_rejected(self, organizer_user):
        client = auth_client(organizer_user)
        start = timezone.now() + timedelta(days=5)
        payload = _event_payload(
            start_datetime=start.isoformat(),
            end_datetime=(start - timedelta(hours=1)).isoformat(),
        )
        response = client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_slug_auto_generated(self, organizer_user):
        client = auth_client(organizer_user)
        response = client.post(
            self.url, _event_payload(title="My Great Event"), format="json"
        )
        assert response.data["slug"] == "my-great-event"

    def test_can_upload_cover_image(self, organizer_user):
        client = auth_client(organizer_user)
        buffer = io.BytesIO()
        Image.new("RGB", (10, 10), color="blue").save(buffer, format="PNG")
        buffer.seek(0)
        image = SimpleUploadedFile("cover.png", buffer.read(), content_type="image/png")
        payload = _event_payload()
        payload["cover_image"] = image
        response = client.post(self.url, payload, format="multipart")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["cover_image"] is not None


# ==================================================
# POST /events/ with event_type=sports_match — admin-only
# ==================================================


class TestCreateSportsMatchEvent:
    url = "/events/"

    def _teams(self):
        sport = SportFactory()
        return TeamFactory(sport=sport), TeamFactory(sport=sport)

    def test_admin_can_create_sports_match_event(self, admin_user):
        home, away = self._teams()
        client = auth_client(admin_user)
        payload = _event_payload(
            event_type=Event.EventType.SPORTS_MATCH,
            home_team=str(home.id),
            away_team=str(away.id),
        )
        response = client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["status"] == Event.Status.APPROVED

    def test_organizer_cannot_create_sports_match_event(self, organizer_user):
        home, away = self._teams()
        client = auth_client(organizer_user)
        payload = _event_payload(
            event_type=Event.EventType.SPORTS_MATCH,
            home_team=str(home.id),
            away_team=str(away.id),
        )
        response = client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_sports_match_requires_both_teams(self, admin_user):
        home, _away = self._teams()
        client = auth_client(admin_user)
        payload = _event_payload(
            event_type=Event.EventType.SPORTS_MATCH, home_team=str(home.id)
        )
        response = client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_sports_match_teams_must_differ(self, admin_user):
        home, _away = self._teams()
        client = auth_client(admin_user)
        payload = _event_payload(
            event_type=Event.EventType.SPORTS_MATCH,
            home_team=str(home.id),
            away_team=str(home.id),
        )
        response = client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_teams_from_different_sports_rejected(self, admin_user):
        home = TeamFactory(sport=SportFactory())
        away = TeamFactory(sport=SportFactory())
        client = auth_client(admin_user)
        payload = _event_payload(
            event_type=Event.EventType.SPORTS_MATCH,
            home_team=str(home.id),
            away_team=str(away.id),
        )
        response = client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_general_event_cannot_set_home_team(self, admin_user):
        home, away = self._teams()
        client = auth_client(admin_user)
        payload = _event_payload(
            event_type=Event.EventType.GENERAL,
            home_team=str(home.id),
            away_team=str(away.id),
        )
        response = client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_organizer_cannot_convert_own_event_to_sports_match(self, organizer_user):
        home, away = self._teams()
        event = EventFactory(
            organizer=organizer_user,
            event_type=Event.EventType.GENERAL,
            status=Event.Status.PENDING_APPROVAL,
        )
        client = auth_client(organizer_user)
        response = client.patch(
            f"/events/{event.pk}/",
            {
                "event_type": Event.EventType.SPORTS_MATCH,
                "home_team": str(home.id),
                "away_team": str(away.id),
            },
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ==================================================
# PATCH /events/{id}/ (update)
# ==================================================


class TestUpdateEvent:
    def test_owner_can_update_own_event(self, organizer_user):
        event = EventFactory(organizer=organizer_user, status=Event.Status.APPROVED)
        client = auth_client(organizer_user)
        response = client.patch(
            f"/events/{event.pk}/", {"title": "Updated"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Updated"

    def test_non_owner_organizer_cannot_update(self, organizer_user):
        other = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(organizer=other, status=Event.Status.APPROVED)
        client = auth_client(organizer_user)
        response = client.patch(
            f"/events/{event.pk}/", {"title": "Hijacked"}, format="json"
        )
        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )

    def test_admin_cannot_update_organizers_event(self, admin_user):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(organizer=organizer, status=Event.Status.APPROVED)
        client = auth_client(admin_user)
        response = client.patch(
            f"/events/{event.pk}/", {"title": "Admin Edit"}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_update_own_event(self, admin_user):
        event = EventFactory(organizer=admin_user, status=Event.Status.APPROVED)
        client = auth_client(admin_user)
        response = client.patch(
            f"/events/{event.pk}/", {"title": "Admin Self Edit"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_sensitive_field_update_retriggers_approval(self, organizer_user):
        event = EventFactory(organizer=organizer_user, status=Event.Status.APPROVED)
        new_venue = VenueFactory()
        client = auth_client(organizer_user)
        response = client.patch(
            f"/events/{event.pk}/", {"venue": str(new_venue.id)}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == Event.Status.PENDING_APPROVAL

    def test_cosmetic_field_update_does_not_retrigger_approval(self, organizer_user):
        event = EventFactory(organizer=organizer_user, status=Event.Status.APPROVED)
        client = auth_client(organizer_user)
        response = client.patch(
            f"/events/{event.pk}/", {"description": "New copy."}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == Event.Status.APPROVED

    def test_cannot_update_completed_event(self, organizer_user):
        event = EventFactory(organizer=organizer_user, status=Event.Status.COMPLETED)
        client = auth_client(organizer_user)
        response = client.patch(
            f"/events/{event.pk}/", {"title": "Too Late"}, format="json"
        )
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_client_supplied_status_is_ignored(self, organizer_user):
        event = EventFactory(organizer=organizer_user, status=Event.Status.APPROVED)
        client = auth_client(organizer_user)
        response = client.patch(
            f"/events/{event.pk}/", {"status": Event.Status.CANCELLED}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == Event.Status.APPROVED

    def test_anonymous_cannot_update(self, api_client):
        event = EventFactory(status=Event.Status.APPROVED)
        response = api_client.patch(
            f"/events/{event.pk}/", {"title": "Nope"}, format="json"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================================================
# DELETE /events/{id}/
# ==================================================


class TestDeleteEvent:
    @pytest.mark.parametrize(
        "blocking_status",
        [Event.Status.PENDING_APPROVAL, Event.Status.APPROVED, Event.Status.REJECTED],
    )
    def test_delete_blocked_for_non_terminal_status(
        self, organizer_user, blocking_status
    ):
        event = EventFactory(organizer=organizer_user, status=blocking_status)
        client = auth_client(organizer_user)
        response = client.delete(f"/events/{event.pk}/")
        assert response.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.parametrize(
        "terminal_status", [Event.Status.CANCELLED, Event.Status.COMPLETED]
    )
    def test_owner_can_soft_delete_terminal_event(
        self, organizer_user, terminal_status
    ):
        event = EventFactory(organizer=organizer_user, status=terminal_status)
        client = auth_client(organizer_user)
        response = client.delete(f"/events/{event.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        event.refresh_from_db()
        assert event.is_active is False

    def test_soft_delete_bumps_updated_at(self, organizer_user):
        event = EventFactory(organizer=organizer_user, status=Event.Status.CANCELLED)
        original_updated_at = event.updated_at
        client = auth_client(organizer_user)
        client.delete(f"/events/{event.pk}/")
        event.refresh_from_db()
        assert event.updated_at > original_updated_at

    def test_non_owner_organizer_cannot_delete(self, organizer_user):
        other = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(organizer=other, status=Event.Status.CANCELLED)
        client = auth_client(organizer_user)
        response = client.delete(f"/events/{event.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_non_owner_organizer_cannot_delete_visible_completed_event(
        self, organizer_user
    ):
        other = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(organizer=other, status=Event.Status.COMPLETED)
        client = auth_client(organizer_user)
        response = client.delete(f"/events/{event.pk}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_delete_organizers_event(self, admin_user):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(organizer=organizer, status=Event.Status.CANCELLED)
        client = auth_client(admin_user)
        response = client.delete(f"/events/{event.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_hard_delete_removes_row(self, admin_user):
        event = EventFactory(organizer=admin_user, status=Event.Status.CANCELLED)
        client = auth_client(admin_user)
        response = client.delete(f"/events/{event.pk}/?hard=true")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Event.all_objects.filter(id=event.id).exists()

    def test_hard_delete_still_enforces_status_precondition(self, admin_user):
        event = EventFactory(organizer=admin_user, status=Event.Status.APPROVED)
        client = auth_client(admin_user)
        response = client.delete(f"/events/{event.pk}/?hard=true")
        assert response.status_code == status.HTTP_409_CONFLICT
        assert Event.all_objects.filter(id=event.id).exists()

    def test_hard_delete_still_enforces_ownership(self, organizer_user):
        other = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(organizer=other, status=Event.Status.COMPLETED)
        client = auth_client(organizer_user)
        response = client.delete(f"/events/{event.pk}/?hard=true")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert Event.all_objects.filter(id=event.id).exists()

    def test_anonymous_cannot_delete(self, api_client):
        event = EventFactory(status=Event.Status.CANCELLED)
        response = api_client.delete(f"/events/{event.pk}/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================================================
# POST /events/{id}/restore/
# ==================================================


class TestRestoreEvent:
    def test_admin_can_restore(self, admin_client):
        event = EventFactory(status=Event.Status.CANCELLED)
        event.is_active = False
        event.save(update_fields=["is_active"])
        response = admin_client.post(f"/events/{event.pk}/restore/")
        assert response.status_code == status.HTTP_200_OK
        event.refresh_from_db()
        assert event.is_active is True

    def test_organizer_cannot_restore(self, organizer_user):
        event = EventFactory(organizer=organizer_user, status=Event.Status.CANCELLED)
        event.is_active = False
        event.save(update_fields=["is_active"])
        client = auth_client(organizer_user)
        response = client.post(f"/events/{event.pk}/restore/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_restore_nonexistent_event_returns_404(self, admin_client):
        response = admin_client.post(
            "/events/00000000-0000-0000-0000-000000000000/restore/"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_restore_already_active_event_returns_409(self, admin_client):
        event = EventFactory(status=Event.Status.CANCELLED)
        response = admin_client.post(f"/events/{event.pk}/restore/")
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_restore_blocked_by_active_slug_collision(self, admin_client):
        inactive = EventFactory(title="Shared Title", status=Event.Status.CANCELLED)
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])
        EventFactory(title="Shared Title")

        response = admin_client.post(f"/events/{inactive.pk}/restore/")
        assert response.status_code == status.HTTP_409_CONFLICT


# ==================================================
# POST /admin/events/{id}/approve/, POST /admin/events/{id}/reject/
# ==================================================


class TestApproveRejectEvent:
    def test_admin_can_approve_pending_event(self, admin_client):
        event = EventFactory(status=Event.Status.PENDING_APPROVAL)
        response = admin_client.post(f"/admin/events/{event.pk}/approve/")
        assert response.status_code == status.HTTP_200_OK
        event.refresh_from_db()
        assert event.status == Event.Status.APPROVED

    def test_approve_bumps_updated_at(self, admin_client):
        event = EventFactory(status=Event.Status.PENDING_APPROVAL)
        original_updated_at = event.updated_at
        admin_client.post(f"/admin/events/{event.pk}/approve/")
        event.refresh_from_db()
        assert event.updated_at > original_updated_at

    def test_admin_can_reject_pending_event(self, admin_client):
        event = EventFactory(status=Event.Status.PENDING_APPROVAL)
        response = admin_client.post(f"/admin/events/{event.pk}/reject/")
        assert response.status_code == status.HTTP_200_OK
        event.refresh_from_db()
        assert event.status == Event.Status.REJECTED

    def test_reject_bumps_updated_at(self, admin_client):
        event = EventFactory(status=Event.Status.PENDING_APPROVAL)
        original_updated_at = event.updated_at
        admin_client.post(f"/admin/events/{event.pk}/reject/")
        event.refresh_from_db()
        assert event.updated_at > original_updated_at

    def test_approve_already_approved_event_returns_409(self, admin_client):
        event = EventFactory(status=Event.Status.APPROVED)
        response = admin_client.post(f"/admin/events/{event.pk}/approve/")
        assert response.status_code == status.HTTP_409_CONFLICT
        event.refresh_from_db()
        assert event.status == Event.Status.APPROVED

    def test_reject_already_rejected_event_returns_409(self, admin_client):
        event = EventFactory(status=Event.Status.REJECTED)
        response = admin_client.post(f"/admin/events/{event.pk}/reject/")
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_approve_cancelled_event_returns_409(self, admin_client):
        event = EventFactory(status=Event.Status.CANCELLED)
        response = admin_client.post(f"/admin/events/{event.pk}/approve/")
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_organizer_cannot_approve(self, organizer_user):
        event = EventFactory(status=Event.Status.PENDING_APPROVAL)
        client = auth_client(organizer_user)
        response = client.post(f"/admin/events/{event.pk}/approve/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_organizer_cannot_reject(self, organizer_user):
        event = EventFactory(status=Event.Status.PENDING_APPROVAL)
        client = auth_client(organizer_user)
        response = client.post(f"/admin/events/{event.pk}/reject/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_approve(self, api_client):
        event = EventFactory(status=Event.Status.PENDING_APPROVAL)
        response = api_client.post(f"/admin/events/{event.pk}/approve/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================================================
# GET /events/ — admin ?include_inactive=true
# ==================================================


class TestIncludeInactiveFilter:
    def test_admin_without_flag_does_not_see_soft_deleted_event(self, admin_client):
        event = EventFactory(status=Event.Status.CANCELLED)
        event.is_active = False
        event.save(update_fields=["is_active"])

        response = admin_client.get("/events/")
        titles = {e["title"] for e in results(response)}
        assert event.title not in titles

    def test_admin_with_flag_sees_soft_deleted_event(self, admin_client):
        event = EventFactory(status=Event.Status.CANCELLED, title="Soft Deleted")
        event.is_active = False
        event.save(update_fields=["is_active"])

        response = admin_client.get("/events/", {"include_inactive": "true"})
        titles = {e["title"] for e in results(response)}
        assert "Soft Deleted" in titles

    def test_organizer_with_flag_does_not_see_soft_deleted_event(self, organizer_user):
        event = EventFactory(status=Event.Status.CANCELLED, title="Hidden")
        event.is_active = False
        event.save(update_fields=["is_active"])

        client = auth_client(organizer_user)
        response = client.get("/events/", {"include_inactive": "true"})
        titles = {e["title"] for e in results(response)}
        assert "Hidden" not in titles


# ==================================================
# GET/POST /events/{id}/ticket-tiers/
# ==================================================


class TestTicketTiers:
    def test_anyone_can_list_ticket_tiers(self, api_client):
        event = EventFactory(status=Event.Status.APPROVED)
        TicketTierFactory(event=event, name="VIP", price="100.00")
        response = api_client.get(f"/events/{event.pk}/ticket-tiers/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_empty_tier_list_is_valid(self, api_client):
        event = EventFactory(status=Event.Status.APPROVED)
        response = api_client.get(f"/events/{event.pk}/ticket-tiers/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_owner_can_create_tier(self, organizer_user):
        event = EventFactory(organizer=organizer_user)
        client = auth_client(organizer_user)
        response = client.post(
            f"/events/{event.pk}/ticket-tiers/",
            {"name": "General", "price": "25.00"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert TicketTier.objects.filter(event=event, name="General").exists()

    def test_non_owner_cannot_create_tier(self, organizer_user):
        other = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(organizer=other)
        client = auth_client(organizer_user)
        response = client.post(
            f"/events/{event.pk}/ticket-tiers/",
            {"name": "General", "price": "25.00"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_cannot_create_tier(self, api_client):
        event = EventFactory()
        response = api_client.post(
            f"/events/{event.pk}/ticket-tiers/",
            {"name": "General", "price": "25.00"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_negative_price_rejected(self, organizer_user):
        event = EventFactory(organizer=organizer_user)
        client = auth_client(organizer_user)
        response = client.post(
            f"/events/{event.pk}/ticket-tiers/",
            {"name": "General", "price": "-1.00"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_create_tier_on_completed_event(self, organizer_user):
        event = EventFactory(organizer=organizer_user, status=Event.Status.COMPLETED)
        client = auth_client(organizer_user)
        response = client.post(
            f"/events/{event.pk}/ticket-tiers/",
            {"name": "Late Tier", "price": "10.00"},
            format="json",
        )
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_owner_can_update_tier_price(self, organizer_user):
        event = EventFactory(organizer=organizer_user, status=Event.Status.APPROVED)
        tier = TicketTierFactory(event=event, price="10.00")
        client = auth_client(organizer_user)
        response = client.patch(
            f"/events/{event.pk}/ticket-tiers/{tier.pk}/",
            {"price": "15.00"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["price"] == "15.00"

    def test_price_update_retriggers_event_approval(self, organizer_user):
        event = EventFactory(organizer=organizer_user, status=Event.Status.APPROVED)
        original_event_updated_at = event.updated_at
        tier = TicketTierFactory(event=event, price="10.00")
        client = auth_client(organizer_user)
        client.patch(
            f"/events/{event.pk}/ticket-tiers/{tier.pk}/",
            {"price": "15.00"},
            format="json",
        )
        event.refresh_from_db()
        assert event.status == Event.Status.PENDING_APPROVAL
        assert event.updated_at > original_event_updated_at

    def test_non_owner_cannot_update_tier(self, organizer_user):
        other = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(organizer=other)
        tier = TicketTierFactory(event=event)
        client = auth_client(organizer_user)
        response = client.patch(
            f"/events/{event.pk}/ticket-tiers/{tier.pk}/",
            {"price": "999.00"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_updating_tier_belonging_to_different_event_in_url_returns_404(
        self, organizer_user
    ):
        event = EventFactory(organizer=organizer_user)
        other_event_tier = TicketTierFactory()
        client = auth_client(organizer_user)
        response = client.patch(
            f"/events/{event.pk}/ticket-tiers/{other_event_tier.pk}/",
            {"price": "1.00"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_price_update_blocked_once_seats_instantiated(self, organizer_user):
        event = EventFactory(organizer=organizer_user, status=Event.Status.APPROVED)
        tier = TicketTierFactory(event=event, price="10.00")
        client = auth_client(organizer_user)

        with patch(
            "apps.events.serializers.ensure_tier_price_mutable",
            side_effect=TierPriceImmutableError("Seats already instantiated."),
        ):
            response = client.patch(
                f"/events/{event.pk}/ticket-tiers/{tier.pk}/",
                {"price": "15.00"},
                format="json",
            )
        assert response.status_code == status.HTTP_409_CONFLICT
        tier.refresh_from_db()
        assert str(tier.price) == "10.00"

    def test_non_price_tier_update_not_blocked_by_immutability_guard(
        self, organizer_user
    ):
        event = EventFactory(organizer=organizer_user, status=Event.Status.APPROVED)
        tier = TicketTierFactory(event=event, name="VIP", price="10.00")
        client = auth_client(organizer_user)
        response = client.patch(
            f"/events/{event.pk}/ticket-tiers/{tier.pk}/",
            {"name": "VIP Plus"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

    def test_malformed_tier_id_in_url_returns_404_not_500(self, organizer_user):
        event = EventFactory(organizer=organizer_user, status=Event.Status.APPROVED)
        client = auth_client(organizer_user)
        response = client.patch(
            f"/events/{event.pk}/ticket-tiers/not-a-real-uuid/",
            {"price": "5.00"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ==================================================
# POST /events/{id}/ticket-tiers/{tier_id}/sections/
# ==================================================


class TestTierSectionMappings:
    def test_owner_can_create_section_mapping(self, organizer_user):
        event = EventFactory(organizer=organizer_user)
        tier = TicketTierFactory(event=event)
        client = auth_client(organizer_user)
        response = client.post(
            f"/events/{event.pk}/ticket-tiers/{tier.pk}/sections/",
            {"section": "A"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert TierSectionMapping.objects.filter(
            event=event, ticket_tier=tier, section="A"
        ).exists()

    def test_duplicate_section_for_same_event_returns_409_or_400(self, organizer_user):
        event = EventFactory(organizer=organizer_user)
        tier = TicketTierFactory(event=event)
        TierSectionMappingFactory(event=event, ticket_tier=tier, section="A")
        client = auth_client(organizer_user)
        response = client.post(
            f"/events/{event.pk}/ticket-tiers/{tier.pk}/sections/",
            {"section": "A"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_owner_cannot_create_section_mapping(self, organizer_user):
        other = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(organizer=other)
        tier = TicketTierFactory(event=event)
        client = auth_client(organizer_user)
        response = client.post(
            f"/events/{event.pk}/ticket-tiers/{tier.pk}/sections/",
            {"section": "A"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_section_mapping_for_tier_from_different_event_returns_404(
        self, organizer_user
    ):
        event = EventFactory(organizer=organizer_user)
        foreign_tier = TicketTierFactory()
        client = auth_client(organizer_user)
        response = client.post(
            f"/events/{event.pk}/ticket-tiers/{foreign_tier.pk}/sections/",
            {"section": "A"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_malformed_tier_id_in_url_returns_404_not_500(self, organizer_user):
        event = EventFactory(organizer=organizer_user)
        client = auth_client(organizer_user)
        response = client.post(
            f"/events/{event.pk}/ticket-tiers/not-a-real-uuid/sections/",
            {"section": "A"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_add_section_mapping_on_completed_event(self, organizer_user):
        event = EventFactory(organizer=organizer_user, status=Event.Status.COMPLETED)
        tier = TicketTierFactory(event=event)
        client = auth_client(organizer_user)
        response = client.post(
            f"/events/{event.pk}/ticket-tiers/{tier.pk}/sections/",
            {"section": "A"},
            format="json",
        )
        assert response.status_code == status.HTTP_409_CONFLICT
