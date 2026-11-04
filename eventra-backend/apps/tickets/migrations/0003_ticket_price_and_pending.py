from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    """A ticket is the one record of a purchased seat: pending until paid, with its price."""

    dependencies = [
        ("tickets", "0002_one_active_ticket_per_seat"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="price",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0.00"), max_digits=10
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="ticket",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Awaiting payment"),
                    ("valid", "Valid"),
                    ("used", "Used"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.RemoveField(model_name="ticket", name="attendee_name"),
        migrations.AddConstraint(
            model_name="ticket",
            constraint=models.UniqueConstraint(
                fields=("booking", "event_seat"), name="uniq_ticket_booking_seat"
            ),
        ),
    ]
