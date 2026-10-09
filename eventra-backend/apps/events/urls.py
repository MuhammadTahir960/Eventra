from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.seating.views import (
    EventSeatHoldView,
    EventSeatInstantiateView,
    EventSeatListView,
)

from .views import (
    EventApproveView,
    EventPendingListView,
    EventRejectView,
    EventRetryRefundsView,
    EventViewSet,
    OrganizerEventListView,
)

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
    path(
        "organizer/events/",
        OrganizerEventListView.as_view(),
        name="organizer-events",
    ),
    path(
        "admin/events/pending/",
        EventPendingListView.as_view(),
        name="admin-events-pending",
    ),
    path(
        "admin/events/<uuid:event_id>/approve/",
        EventApproveView.as_view(),
        name="admin-event-approve",
    ),
    path(
        "admin/events/<uuid:event_id>/reject/",
        EventRejectView.as_view(),
        name="admin-event-reject",
    ),
    path(
        "admin/events/<uuid:event_id>/retry-refunds/",
        EventRetryRefundsView.as_view(),
        name="admin-event-retry-refunds",
    ),
]
