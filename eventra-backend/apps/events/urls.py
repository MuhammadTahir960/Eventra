from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.seating.views import (
    EventSeatHoldView,
    EventSeatInstantiateView,
    EventSeatListView,
)

from .views import EventViewSet

router = DefaultRouter()
router.register("events", EventViewSet, basename="event")

urlpatterns = router.urls + [
    path(
        "events/<uuid:event_id>/seats/",
        EventSeatListView.as_view(),
        name="event-seats",
    ),
    path(
        "events/<uuid:event_id>/seats/instantiate/",
        EventSeatInstantiateView.as_view(),
        name="event-seats-instantiate",
    ),
    path(
        "events/<uuid:event_id>/seats/hold/",
        EventSeatHoldView.as_view(),
        name="event-seats-hold",
    ),
]
