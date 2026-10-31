from django.db import migrations
from django.db.models import Q
from django.utils.text import slugify

FINAL_CATEGORIES = [
    "Concerts & Live Music",
    "Qawwali & Sufi Nights",
    "Stand-up Comedy",
    "Sports",
    "Combat Sports",
    "Esports & Gaming",
    "Workshops & Classes",
    "Conferences & Talks",
    "Theatre & Drama",
    "Mushaira & Literature",
    "Festivals",
    "Food & Drink",
    "Art & Exhibitions",
    "Family & Kids",
]
ADMIN_ONLY = {"Sports"}
RENAMES = {
    "Music": "Concerts & Live Music",
    "Theatre": "Theatre & Drama",
    "Comedy": "Stand-up Comedy",
    "Workshops": "Workshops & Classes",
}


def add_final_categories(apps, schema_editor):
    Category = apps.get_model("categories", "Category")
    active = Category._base_manager.filter(is_active=True)

    for old, new in RENAMES.items():
        if active.filter(name__iexact=new).exists():
            continue
        active.filter(name__iexact=old).update(name=new, slug=slugify(new))

    for order, name in enumerate(FINAL_CATEGORIES):
        fields = {"sort_order": order, "admin_only": name in ADMIN_ONLY}
        same = Q(name__iexact=name) | Q(slug=slugify(name))
        if not active.filter(same).update(**fields):
            Category._base_manager.create(name=name, slug=slugify(name), **fields)


class Migration(migrations.Migration):

    dependencies = [
        ("categories", "0002_category_admin_only"),
    ]

    operations = [
        migrations.RunPython(add_final_categories, migrations.RunPython.noop),
    ]
