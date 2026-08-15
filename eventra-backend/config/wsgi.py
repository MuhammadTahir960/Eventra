"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

if "DJANGO_SETTINGS_MODULE" not in os.environ:
    raise RuntimeError(
        "DJANGO_SETTINGS_MODULE must be set explicitly before starting the WSGI "
        "server — Set it to config.settings.prod (or config.settings.dev for "
        "local testing) in the environment."
    )

application = get_wsgi_application()
