from django.db import migrations, models

from apps.venues.models import COUNTRY_CHOICES


class Migration(migrations.Migration):
    dependencies = [
        ("venues", "0006_drop_duplicate_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="venue",
            name="country",
            field=models.CharField(choices=COUNTRY_CHOICES, max_length=2),
        ),
        migrations.AddField(
            model_name="venue",
            name="time_zone",
            field=models.CharField(default="UTC", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="venuerequest",
            name="country",
            field=models.CharField(choices=COUNTRY_CHOICES, default="GB", max_length=2),
            preserve_default=False,
        ),
    ]
