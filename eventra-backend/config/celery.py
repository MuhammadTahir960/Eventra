import os
from celery import Celery

if "DJANGO_SETTINGS_MODULE" not in os.environ:
    raise RuntimeError(
        "DJANGO_SETTINGS_MODULE must be set explicitly before starting Celery — "
        "Set it to config.settings.prod (or config.settings.dev for local testing) "
        "in the environment."
    )

app = Celery("eventra")

app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
