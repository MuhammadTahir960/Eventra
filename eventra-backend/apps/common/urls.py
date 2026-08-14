from django.urls import path

from .views import HealthCheckView

urlpatterns = [
    path("healthz/", HealthCheckView.as_view(), name="health-check"),
]
