from django.urls import path

from .views import AdminEventPartialRefundsView, StripeWebhookView

urlpatterns = [
    path(
        "admin/events/<uuid:event_id>/partial-refunds/",
        AdminEventPartialRefundsView.as_view(),
        name="admin-event-partial-refunds",
    ),
    path("webhooks/stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]
