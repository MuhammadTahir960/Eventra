import logging

from django.db.models import Sum
from django.http import HttpResponse
from rest_framework import generics, permissions, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdmin
from apps.events.models import Event

from .models import Payment, RefundItem
from .serializers import PartialRefundSerializer
from .services import (
    PaymentNotFoundError,
    RefundNotAllowedError,
    WebhookSignatureError,
    confirm_payment_from_webhook,
    mark_payment_from_webhook,
    refund_part_of_event,
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


class AdminEventPartialRefundsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request, event_id):
        event = generics.get_object_or_404(Event.all_objects, pk=event_id)
        serializer = PartialRefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            refunds = refund_part_of_event(event, serializer.validated_data["percent"])
        except RefundNotAllowedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        total = RefundItem.objects.filter(refund__in=refunds).aggregate(
            total=Sum("amount")
        )["total"]
        return Response(
            {"refunds": len(refunds), "amount": str(total or "0.00")},
            status=status.HTTP_201_CREATED,
        )
