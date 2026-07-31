from rest_framework.routers import DefaultRouter
from .views import VenueViewSet

router = DefaultRouter()
router.register("venues", VenueViewSet, basename="venue")

urlpatterns = router.urls
