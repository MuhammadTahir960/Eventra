from django.db import migrations

ICONS = {
    "Concerts & Live Music": "music",
    "Qawwali & Sufi Nights": "microphone",
    "Stand-up Comedy": "laugh",
    "Sports": "football",
    "Combat Sports": "boxing",
    "Esports & Gaming": "gamepad",
    "Workshops & Classes": "tools",
    "Conferences & Talks": "presentation",
    "Theatre & Drama": "theatre",
    "Mushaira & Literature": "quill",
    "Festivals": "party",
    "Food & Drink": "food",
    "Art & Exhibitions": "palette",
    "Family & Kids": "balloons",
}


def set_category_icons(apps, schema_editor):
    Category = apps.get_model("categories", "Category")
    for name, icon in ICONS.items():
        Category._base_manager.filter(name__iexact=name).update(icon=icon)
    Category._base_manager.exclude(icon__in=ICONS.values()).update(icon="ticket")


class Migration(migrations.Migration):

    dependencies = [
        ("categories", "0004_category_icon_choices"),
    ]

    operations = [
        migrations.RunPython(set_category_icons, migrations.RunPython.noop),
    ]
