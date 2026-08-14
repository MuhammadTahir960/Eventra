"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter
from django.core.asgi import get_asgi_application

if "DJANGO_SETTINGS_MODULE" not in os.environ:
    raise RuntimeError(
        "DJANGO_SETTINGS_MODULE must be set explicitly before starting the ASGI "
        "server — Set it to config.settings.prod (or config.settings.dev for local "
        "Daphne testing) in the environment."
    )

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
    }
)
