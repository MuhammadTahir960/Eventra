from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    CountryListView,
    VenueRequestFulfilView,
    VenueRequestListCreateView,
    VenueRequestRejectView,
    VenueViewSet,
)

router = SimpleRouter()
router.register("venues", VenueViewSet, basename="venue")

urlpatterns = [
    path("countries/", CountryListView.as_view(), name="country-list"),
    path(
        "venues/requests/",
        VenueRequestListCreateView.as_view(),
        name="venue-requests-list-create",
    ),
    path(
        "venues/requests/<uuid:request_id>/reject/",
        VenueRequestRejectView.as_view(),
        name="venue-request-reject",
    ),
    path(
        "venues/requests/<uuid:request_id>/fulfil/",
        VenueRequestFulfilView.as_view(),
        name="venue-request-fulfil",
    ),
] + router.urls
