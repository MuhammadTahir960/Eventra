from django.urls import path

from .views import (
    AdminEventPayOutView,
    AdminPartnerListView,
    AdminPayoutListView,
    AdminPayoutReadyListView,
    AdminPayoutSettleView,
    OrganizerEventSalesView,
    OrganizerPayoutListView,
    OrganizerPayoutUpcomingListView,
    PayoutAccountNumberView,
)

urlpatterns = [
    path(
        "payout-account-numbers/",
        PayoutAccountNumberView.as_view(),
        name="payout-account-numbers",
    ),
    path("admin/partners/", AdminPartnerListView.as_view(), name="admin-partner-list"),
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
        "organizer/payouts/upcoming/",
        OrganizerPayoutUpcomingListView.as_view(),
        name="organizer-payout-upcoming",
    ),
    path(
        "admin/payouts/ready/",
        AdminPayoutReadyListView.as_view(),
        name="admin-payout-ready",
    ),
    path(
        "admin/events/<uuid:event_id>/payouts/",
        AdminEventPayOutView.as_view(),
        name="admin-event-payouts",
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
