from django.urls import path

from .views import (
    TicketCheckInView,
    TicketDetailView,
    TicketDownloadView,
    TicketListView,
)

urlpatterns = [
    path("tickets/", TicketListView.as_view(), name="ticket-list"),
    path("tickets/<uuid:id>/", TicketDetailView.as_view(), name="ticket-detail"),
    path(
        "tickets/<uuid:id>/download/",
        TicketDownloadView.as_view(),
        name="ticket-download",
    ),
    path(
        "events/<uuid:event_id>/check-ins/",
        TicketCheckInView.as_view(),
        name="event-check-ins",
    ),
]
