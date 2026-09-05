from django.urls import path

from .views import (
    TicketDetailView,
    TicketDownloadView,
    TicketListView,
    TicketValidateView,
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
        "events/<uuid:event_id>/tickets/<uuid:ticket_id>/validate/",
        TicketValidateView.as_view(),
        name="ticket-validate",
    ),
]
