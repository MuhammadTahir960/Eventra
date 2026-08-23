import factory

from apps.bookings.factories import BookingFactory

from .models import Payment


class PaymentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Payment

    booking = factory.SubFactory(BookingFactory)
    stripe_payment_intent_id = factory.Sequence(lambda n: f"pi_test_{n:012d}")
    client_secret = factory.LazyAttribute(
        lambda o: f"{o.stripe_payment_intent_id}_secret_test"
    )
    amount = 4999
    currency = "usd"
    status = Payment.Status.PENDING
