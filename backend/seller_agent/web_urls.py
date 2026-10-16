from django.urls import path
from . import views

urlpatterns = [path("", views.desk, name="seller_ai"), path("link/", views.link),
               path("mini-preview/", views.mini_preview)]
