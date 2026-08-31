from django.urls import path

from .views import InternalSeatsBroadcastView

urlpatterns = [
    path(
        "internal/seats/broadcast/",
        InternalSeatsBroadcastView.as_view(),
        name="internal-seats-broadcast",
    ),
]
