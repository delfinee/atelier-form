from django.urls import path
from .customer import preview

urlpatterns = [path("", preview)]
