from django.urls import path

from . import views

urlpatterns = [
    # `.jpg` is cosmetic -- it makes the URL look like a file to caches, proxies
    # and anyone reading the markup. The real content type comes from the row.
    path("img/<slug:name>.jpg", views.site_image, name="site_image"),
    path("credits/", views.credits, name="image_credits"),
]
