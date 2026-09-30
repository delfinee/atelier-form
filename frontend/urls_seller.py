"""Seller portal routes."""

from django.urls import path
from . import views_seller

app_name = "seller"

urlpatterns = [
    path("products/", views_seller.seller_product_list, name="product_list"),
    path("products/add/", views_seller.seller_product_create, name="product_create"),
    path("products/<slug:slug>/edit/", views_seller.seller_product_edit, name="product_edit"),
    path("orders/", views_seller.seller_order_list, name="order_list"),
]
