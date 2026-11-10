from django.urls import path

from .views import (
    BookingCheckoutView,
    BookingDetailView,
    BookingListCreateView,
    BookingRefundsView,
)

urlpatterns = [
    path("bookings/", BookingListCreateView.as_view(), name="booking-list-create"),
    path("bookings/<uuid:id>/", BookingDetailView.as_view(), name="booking-detail"),
    path(
        "bookings/<uuid:id>/checkout/",
        BookingCheckoutView.as_view(),
        name="booking-checkout",
    ),
    path(
        "bookings/<uuid:id>/refunds/",
        BookingRefundsView.as_view(),
        name="booking-refunds",
    ),
]
