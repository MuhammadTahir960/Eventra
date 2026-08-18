from django.urls import re_path

from .consumers import SeatConsumer

websocket_urlpatterns = [
    re_path(r"^ws/seats/(?P<event_slug>[-\w]+)/$", SeatConsumer.as_asgi()),
]
