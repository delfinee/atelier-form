from django.urls import path
from . import api

urlpatterns = [
    path("status/", api.Status.as_view()), path("session/login/", api.Login.as_view()),
    path("session/developer/", api.DeveloperLogin.as_view()), path("session/logout/", api.Logout.as_view()),
    path("me/", api.Me.as_view()), path("link/start/", api.LinkStart.as_view()),
    path("link/approve/", api.LinkApprove.as_view()), path("links/", api.Links.as_view()),
    path("links/<uuid:uuid>/unlink/", api.Unlink.as_view()),
    path("conversations/", api.Conversations.as_view()), path("conversations/<uuid:uuid>/", api.Detail.as_view()),
    path("conversations/<uuid:uuid>/messages/", api.Chat.as_view()),
    path("conversations/<uuid:uuid>/changes/", api.Prepare.as_view()),
    path("changes/<uuid:uuid>/confirm/", api.Confirm.as_view()), path("snapshot/", api.Snapshot.as_view()),
]
