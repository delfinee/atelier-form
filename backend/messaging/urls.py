"""URLs for messaging API."""

from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("", api.ConversationViewSet, basename="conversation")

urlpatterns = router.urls
