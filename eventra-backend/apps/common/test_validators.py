import io
import os

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common import validators
from apps.sports.factories import LeagueFactory, TeamFactory
from apps.users.factories import UserFactory
from apps.venues.factories import VenueFactory

from .validators import MAX_IMAGE_UPLOAD_SIZE_MB

pytestmark = pytest.mark.django_db


def _admin_client():
    admin = UserFactory(role="admin", is_staff=True)
    client = APIClient()
    access = RefreshToken.for_user(admin).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _valid_png(name="photo.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="blue").save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type="image/png")


def _oversized_png(name="huge.png"):
    width = height = 1600
    raw = os.urandom(width * height * 3)
    buffer = io.BytesIO()
    Image.frombytes("RGB", (width, height), raw).save(buffer, format="PNG")
    buffer.seek(0)
    content = buffer.read()
    assert len(content) > MAX_IMAGE_UPLOAD_SIZE_MB * 1024 * 1024
    return SimpleUploadedFile(name, content, content_type="image/png")


def _disallowed_extension_file(name="notes.txt"):
    return SimpleUploadedFile(name, b"not an image at all", content_type="text/plain")


def _venue_case():
    venue = VenueFactory()
    return f"/venues/{venue.pk}/", "photo"


def _team_case():
    team = TeamFactory()
    return f"/teams/{team.pk}/", "logo"


def _league_case():
    league = LeagueFactory()
    return f"/leagues/{league.pk}/", "logo"


IMAGE_FIELD_CASES = [
    pytest.param(_venue_case, id="venue-photo"),
    pytest.param(_team_case, id="team-logo"),
    pytest.param(_league_case, id="league-logo"),
]


@pytest.mark.parametrize("case_factory", IMAGE_FIELD_CASES)
def test_oversized_image_rejected_with_400(case_factory):
    url, field_name = case_factory()
    client = _admin_client()

    response = client.patch(url, {field_name: _oversized_png()}, format="multipart")

    assert response.status_code == 400
    assert field_name in response.data


@pytest.mark.parametrize("case_factory", IMAGE_FIELD_CASES)
def test_disallowed_extension_rejected_with_400(case_factory):
    url, field_name = case_factory()
    client = _admin_client()

    response = client.patch(
        url, {field_name: _disallowed_extension_file()}, format="multipart"
    )

    assert response.status_code == 400
    assert field_name in response.data


@pytest.mark.parametrize("case_factory", IMAGE_FIELD_CASES)
def test_valid_image_round_trips_through_storage(case_factory):
    url, field_name = case_factory()
    client = _admin_client()

    response = client.patch(url, {field_name: _valid_png()}, format="multipart")

    assert response.status_code == 200, response.data
    assert response.data[field_name]


def _png(width, height):
    buffer = io.BytesIO()
    Image.new("1", (width, height)).save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile("x.png", buffer.read(), content_type="image/png")


class TestImagePixelCap:
    def test_normal_image_passes(self):
        validators.validate_image_upload_size(_png(100, 100))

    def test_tiny_file_that_decodes_to_a_huge_image_is_rejected(self):
        bomb = _png(6000, 6000)
        assert bomb.size < 1024 * 1024
        with pytest.raises(ValidationError):
            validators.validate_image_upload_size(bomb)

    def test_non_image_bytes_are_left_to_the_imagefield_check(self):
        validators.validate_image_upload_size(
            SimpleUploadedFile("x.png", b"not an image")
        )

    def test_decompression_bomb_is_rejected_not_swallowed(self, monkeypatch):
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1_000)
        with pytest.raises(ValidationError):
            validators.validate_image_upload_size(_png(100, 100))

    def test_file_pointer_is_rewound_after_a_rejected_image(self, monkeypatch):
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1_000)
        bomb = _png(100, 100)
        with pytest.raises(ValidationError):
            validators.validate_image_upload_size(bomb)
        assert bomb.tell() == 0
