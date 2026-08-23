import stripe
from django.conf import settings
from django.db import IntegrityError, transaction

from .models import Payment

stripe.api_key = settings.STRIPE_SECRET_KEY

CURRENCY = "usd"


class PaymentGatewayError(Exception):
    """stripe.PaymentIntent.create() raised stripe.error.StripeError."""


def _to_cents(total_amount):
    return int(round(total_amount * 100))


def create_or_refresh_payment_intent(booking):
    payment = Payment.objects.filter(booking=booking).first()
    if payment is not None and payment.stripe_payment_intent_id:
        return payment

    amount_cents = _to_cents(booking.total_amount)

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=CURRENCY,
            metadata={"booking_id": str(booking.id)},
            idempotency_key=booking.idempotency_key,
        )
    except stripe.error.StripeError as exc:
        raise PaymentGatewayError(
            "Unable to reach the payment provider. Please try again."
        ) from exc

    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(booking=booking).first()

        if payment is not None and payment.stripe_payment_intent_id:
            return payment

        if payment is None:
            try:
                with transaction.atomic():
                    payment = Payment.objects.create(
                        booking=booking,
                        stripe_payment_intent_id=intent.id,
                        client_secret=intent.client_secret,
                        amount=amount_cents,
                        currency=CURRENCY,
                        status=Payment.Status.PENDING,
                    )
            except IntegrityError:
                payment = Payment.objects.get(booking=booking)
        else:
            payment.stripe_payment_intent_id = intent.id
            payment.client_secret = intent.client_secret
            payment.amount = amount_cents
            payment.save(
                update_fields=[
                    "stripe_payment_intent_id",
                    "client_secret",
                    "amount",
                    "updated_at",
                ]
            )

    return payment
