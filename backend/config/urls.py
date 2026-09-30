"""URL map for the frontend.

Paths are the public contract: `mockdata.content.FOOTER_NAV` and the JS layer
both hard-code a few of them, so a rename here needs a matching edit there.
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, reverse_lazy

from frontend import views, views_seller

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),

    # JSON API. Everything under /api/ is documented at /api/docs/.
    path("api/", include("config.api_urls")),

    # Photography served out of PostgreSQL, plus its licence credits.
    path("", include("imagery.urls")),

    path("", views.home, name="home"),

    # Shop & collections
    path("shop/", views.shop, name="shop"),
    path("collections/", views.collections_index, name="collections"),
    path("collections/<slug:slug>/", views.collection_detail, name="collection_detail"),
    path("products/<slug:slug>/", views.product_detail, name="product_detail"),

    # Search
    path("search/", views.search, name="search"),
    path("api/search/", views.search_api, name="search_api"),
    path("api/catalogue/", views.catalogue_api, name="catalogue_api"),

    # Bag & checkout
    path("bag/", views.cart, name="cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/mock-payment/<uuid:uuid>/", views.mock_payment, name="mock_payment"),
    path("checkout/confirmation/<uuid:uuid>/", views.order_confirmation, name="order_confirmation"),

    # Account
    path("account/", views.account_overview, name="account_overview"),
    path("account/orders/", views.account_orders, name="account_orders"),
    path("account/orders/<str:order_id>/", views.account_order_detail, name="account_order_detail"),
    path("account/profile/", views.account_profile, name="account_profile"),
    path("account/change-password/", views.account_change_password, name="account_change_password"),
    path("account/addresses/", views.account_addresses, name="account_addresses"),
    path("account/wishlist/", views.account_wishlist, name="account_wishlist"),
    path("account/addresses/<uuid:uuid>/delete/", views.account_address_delete,
         name="account_address_delete"),
    path("account/login/", views.auth_page, {"mode": "login"}, name="login"),
    path("account/register/", views.auth_page, {"mode": "register"}, name="register"),
    path("account/forgot-password/", auth_views.PasswordResetView.as_view(
        template_name="frontend/account/password_reset_form.html",
        email_template_name="frontend/account/password_reset_email.txt",
        subject_template_name="frontend/account/password_reset_subject.txt",
        success_url=reverse_lazy("password_reset_done"),
    ), name="forgot_password"),
    path("account/password-reset/done/", auth_views.PasswordResetDoneView.as_view(
        template_name="frontend/account/password_reset_done.html",
    ), name="password_reset_done"),
    path("account/reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="frontend/account/password_reset_confirm.html",
        success_url=reverse_lazy("password_reset_complete"),
    ), name="password_reset_confirm"),
    path("account/reset/complete/", auth_views.PasswordResetCompleteView.as_view(
        template_name="frontend/account/password_reset_complete.html",
    ), name="password_reset_complete"),
    path("account/logout/", views.account_logout, name="logout"),

    # Seller surface
    path("seller/", views.seller_dashboard, name="seller_dashboard"),
    path("seller/orders/<str:order_number>/", views.seller_order_detail, name="seller_order_detail"),
    path("seller/products/", views_seller.seller_product_list, name="seller_product_list"),
    path("seller/products/add/", views_seller.seller_product_create, name="seller_product_create"),
    path("seller/products/<slug:slug>/edit/", views_seller.seller_product_edit, name="seller_product_edit"),
    path("seller/orders/", views_seller.seller_order_list, name="seller_order_list"),
    path("seller/", include("frontend.urls_seller", namespace="seller")),

    # Editorial
    path("our-story/", views.our_story, name="our_story"),
    path("makers/", views.makers_index, name="makers"),
    path("makers/<slug:slug>/", views.maker_detail, name="maker_detail"),
    path("journal/", views.journal_index, name="journal"),
    path("journal/<slug:slug>/", views.journal_detail, name="journal_detail"),

    # Informational
    path("contact/", views.contact, name="contact"),
    path("faq/", views.faq, name="faq"),
    path("shipping-returns/", views.shipping_returns, name="shipping_returns"),
    path("care/", views.care_guide, name="care_guide"),
    path("privacy/", views.legal, {"slug": "privacy"}, name="privacy"),
    path("terms/", views.legal, {"slug": "terms"}, name="terms"),

    # Mock form endpoints
    path("api/newsletter/", views.newsletter_signup, name="newsletter_signup"),
]
