import logging

from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .models import Payment
from .services import (
    PaymentNotFoundError,
    WebhookSignatureError,
    confirm_payment_from_webhook,
    mark_payment_from_webhook,
    verify_stripe_webhook_signature,
)

logger = logging.getLogger(__name__)


class StripeWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def post(self, request):
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

        try:
            event = verify_stripe_webhook_signature(request.body, sig_header)
        except WebhookSignatureError:
            logger.warning("Rejected Stripe webhook: invalid signature")
            return HttpResponse(status=400)

        if event["type"] == "payment_intent.succeeded":
            payment_intent_id = event["data"]["object"]["id"]
            try:
                confirm_payment_from_webhook(payment_intent_id)
            except PaymentNotFoundError:
                logger.warning(
                    "Webhook for unknown PaymentIntent %s", payment_intent_id
                )

        elif event["type"] == "payment_intent.payment_failed":
            mark_payment_from_webhook(
                event["data"]["object"]["id"], Payment.Status.FAILED
            )
        elif event["type"] == "payment_intent.canceled":
            mark_payment_from_webhook(
                event["data"]["object"]["id"], Payment.Status.CANCELED
            )

        return HttpResponse(status=200)
