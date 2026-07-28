from rest_framework.routers import DefaultRouter
from .views import LeagueViewSet, SportViewSet, TeamViewSet

router = DefaultRouter()
router.register("sports", SportViewSet, basename="sport")
router.register("leagues", LeagueViewSet, basename="league")
router.register("teams", TeamViewSet, basename="team")

urlpatterns = router.urls
