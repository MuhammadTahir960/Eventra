from django.utils import timezone
from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin

from . import account_numbers
from .models import OrganizerPayout, Partner, PayoutAccount
from .services import event_payout_account, payout_available_at, split_gross_revenue


class PayoutAccountSerializer(RejectUnknownFieldsMixin, serializers.ModelSerializer):
    account_number = serializers.SerializerMethodField()

    class Meta:
        model = PayoutAccount
        fields = ["method", "provider", "holder_name", "account_number"]
        read_only_fields = ["method"]

    def get_account_number(self, account) -> str:
        return account_numbers.masked(account.account_number)


class NewPayoutAccountSerializer(RejectUnknownFieldsMixin, serializers.ModelSerializer):
    number_token = serializers.CharField(write_only=True, max_length=200)

    class Meta:
        model = PayoutAccount
        fields = ["method", "provider", "holder_name", "number_token"]


class PartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Partner
        fields = ["id", "name"]
        read_only_fields = fields


def _paid_to(event) -> dict | None:
    account = event_payout_account(event)
    if account is None:
        return None
    return {
        "name": account.holder_name,
        "provider": account.provider,
        "account_number": account_numbers.masked(account.account_number),
    }


class OrganizerPayoutSerializer(serializers.ModelSerializer):
    event_id = serializers.UUIDField(source="event.id", read_only=True)
    event_title = serializers.CharField(source="event.title", read_only=True)
    currency = serializers.CharField(source="event.currency", read_only=True)
    net_amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )
    paid_to = serializers.SerializerMethodField()

    class Meta:
        model = OrganizerPayout
        fields = [
            "id",
            "event_id",
            "event_title",
            "currency",
            "gross_revenue",
            "platform_fee",
            "net_amount",
            "paid_to",
            "status",
            "settled_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_paid_to(self, payout) -> dict | None:
        return _paid_to(payout.event)


class TicketSaleSerializer(serializers.Serializer):
    ticket_id = serializers.UUIDField(read_only=True)
    ticket_code = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    refunded = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    status = serializers.ChoiceField(choices=["confirmed", "refunded"], read_only=True)


class EventSalesSerializer(serializers.Serializer):
    currency = serializers.CharField(read_only=True)
    tickets_sold = serializers.IntegerField(read_only=True)
    gross_revenue = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )
    tickets = TicketSaleSerializer(many=True, read_only=True)


class AwaitingPayoutSerializer(serializers.Serializer):
    def to_representation(self, event):
        gross, fee, net = split_gross_revenue(event.gross_revenue)
        available_at = payout_available_at(event)
        organizer = event.organizer
        return {
            "event_id": str(event.id),
            "event_title": event.title,
            "organizer_name": str(organizer).strip() or organizer.email,
            "venue_name": event.venue.name if event.venue else "",
            "currency": event.currency,
            "completed_at": serializers.DateTimeField().to_representation(
                event.completed_at
            ),
            "payout_available_at": serializers.DateTimeField().to_representation(
                available_at
            ),
            "eligible": timezone.now() >= available_at,
            "gross_revenue": str(gross),
            "platform_fee": str(fee),
            "net_amount": str(net),
            "paid_to": _paid_to(event),
        }
