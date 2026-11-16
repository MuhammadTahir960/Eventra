from rest_framework.routers import SimpleRouter

from .views import LeagueViewSet, SportViewSet, TeamViewSet

router = SimpleRouter()
router.register("sports", SportViewSet, basename="sport")
router.register("leagues", LeagueViewSet, basename="league")
router.register("teams", TeamViewSet, basename="team")

urlpatterns = router.urls
