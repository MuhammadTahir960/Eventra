from django.urls import path

from .views import (
    AdminPayoutListView,
    AdminPayoutSettleView,
    OrganizerEventSalesView,
    OrganizerPayoutListView,
)

urlpatterns = [
    path(
        "organizer/events/<uuid:event_id>/sales/",
        OrganizerEventSalesView.as_view(),
        name="organizer-event-sales",
    ),
    path(
        "organizer/payouts/",
        OrganizerPayoutListView.as_view(),
        name="organizer-payout-list",
    ),
    path(
        "admin/payouts/",
        AdminPayoutListView.as_view(),
        name="admin-payout-list",
    ),
    path(
        "admin/payouts/<uuid:payout_id>/settle/",
        AdminPayoutSettleView.as_view(),
        name="admin-payout-settle",
    ),
]
