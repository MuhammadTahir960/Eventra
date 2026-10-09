"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import OriginValidator
from django.core.asgi import get_asgi_application

if "DJANGO_SETTINGS_MODULE" not in os.environ:
    raise RuntimeError(
        "DJANGO_SETTINGS_MODULE must be set explicitly before starting the ASGI "
        "server — Set it to config.settings.prod (or config.settings.dev for local "
        "Daphne testing) in the environment."
    )

http_application = get_asgi_application()


from django.conf import settings  # noqa: E402

from apps.seating.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": http_application,
        "websocket": OriginValidator(
            URLRouter(websocket_urlpatterns), settings.CORS_ALLOWED_ORIGINS
        ),
    }
)
