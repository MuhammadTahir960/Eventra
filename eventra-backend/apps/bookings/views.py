from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Booking
from .serializers import (
    BookingSerializer,
    CheckoutResponseSerializer,
    HoldIdSerializer,
)
from .services import (
    BookingNotPendingError,
    HoldExpiredError,
    HoldNotFoundError,
    PaymentGatewayError,
    cancel_booking,
    checkout_booking,
    create_booking_from_hold,
)


class BookingListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Booking.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        return BookingSerializer

    def create(self, request, *args, **kwargs):
        input_serializer = HoldIdSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        hold_id = input_serializer.validated_data["hold_id"]

        try:
            booking, created = create_booking_from_hold(hold_id, request.user)
        except HoldNotFoundError:
            return Response(
                {"detail": "No matching hold found for this hold_id."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except HoldExpiredError:
            return Response(
                {"detail": "This hold has already expired."},
                status=status.HTTP_409_CONFLICT,
            )

        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(BookingSerializer(booking).data, status=response_status)


class BookingDetailView(generics.RetrieveAPIView):
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"
    lookup_url_kwarg = "id"

    def get_queryset(self):
        return Booking.objects.filter(user=self.request.user)


class BookingCheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        booking = generics.get_object_or_404(
            Booking.objects.filter(user=request.user), id=id
        )
        try:
            payment = checkout_booking(booking)
        except BookingNotPendingError:
            return Response(
                {"detail": "Checkout is only available for pending bookings."},
                status=status.HTTP_409_CONFLICT,
            )
        except PaymentGatewayError:
            return Response(
                {"detail": "Unable to reach the payment provider. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            CheckoutResponseSerializer(payment).data, status=status.HTTP_200_OK
        )


class BookingCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        booking = generics.get_object_or_404(
            Booking.objects.filter(user=request.user), id=id
        )
        try:
            booking = cancel_booking(booking)
        except BookingNotPendingError:
            return Response(
                {"detail": "Cancellation is only available for pending bookings."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(BookingSerializer(booking).data, status=status.HTTP_200_OK)
