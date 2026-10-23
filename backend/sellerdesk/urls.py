from django.urls import path
from . import views

urlpatterns = [
    path("", views.desk, name="seller_workbench"),
    path("api/overview/", views.Overview.as_view()),
    path("api/invitations/", views.Invitations.as_view()),
    path("api/conversations/<uuid:uuid>/", views.Detail.as_view()),
    path("api/conversations/<uuid:uuid>/reply/", views.Reply.as_view()),
    path("api/conversations/<uuid:uuid>/quote/", views.Quote.as_view()),
    path("api/conversations/<uuid:uuid>/revoke/", views.Revoke.as_view()),
    path("api/drafts/<uuid:uuid>/action/", views.Action.as_view()),
]
