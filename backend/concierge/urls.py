from django.urls import path
from . import views

urlpatterns = [
    path("", views.desk, name="concierge_desk"),
    path("conversations/", views.conversations),
    path("conversations/<uuid:uuid>/", views.conversation_detail),
    path("conversations/<uuid:uuid>/messages/", views.message),
    path("conversations/<uuid:uuid>/drafts/", views.draft),
    path("drafts/<uuid:uuid>/action/", views.action),
]
