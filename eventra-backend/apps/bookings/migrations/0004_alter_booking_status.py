from django.db import migrations, models


def requeue_failed_refunds(apps, schema_editor):
    Booking = apps.get_model("bookings", "Booking")
    Booking.objects.filter(status="refund_failed").update(status="confirmed")


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0003_alter_booking_idempotency_key_and_more"),
    ]

    operations = [
        migrations.RunPython(requeue_failed_refunds, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="booking",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("confirmed", "Confirmed"),
                    ("cancelled", "Cancelled"),
                    ("refunded", "Refunded"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.RemoveField(model_name="booking", name="total_amount"),
        migrations.RemoveField(model_name="booking", name="idempotency_key"),
    ]
