"""JSON API URL map, mounted at /api/.

Grouped by domain. Each app owns its serializers and views; this module only
wires them together.
"""

from django.db import connection
from django.urls import include, path
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from accounts import api as accounts_api
from content import api as content_api
from orders import api as orders_api
from payments.api import PaymentWebhookView
from products import api as products_api
from reviews import api as reviews_api


@extend_schema(
    summary="Liveness and database connectivity",
    responses={200: {"type": "object",
                     "properties": {"status": {"type": "string"},
                                    "database": {"type": "string"}}}},
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Liveness plus a real database round-trip."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        database = "ok"
    except Exception:
        database = "unavailable"
    payload = {"status": "ok" if database == "ok" else "degraded", "database": database}
    return Response(payload, status=(status.HTTP_200_OK if database == "ok"
                                     else status.HTTP_503_SERVICE_UNAVAILABLE))


router = DefaultRouter()
router.register("products", products_api.ProductViewSet, basename="product")
router.register("categories", products_api.CategoryViewSet, basename="category")
router.register("collections", products_api.CollectionViewSet, basename="collection")
router.register("makers", products_api.MakerViewSet, basename="maker")
router.register("journal", content_api.ArticleViewSet, basename="article")
router.register("faqs/groups", content_api.FAQGroupViewSet, basename="faq-group")
router.register("faqs", content_api.FAQViewSet, basename="faq")
router.register("addresses", accounts_api.AddressViewSet, basename="address")
router.register("wishlist", accounts_api.WishlistViewSet, basename="wishlist")
router.register("orders", orders_api.OrderViewSet, basename="order")
router.register("reviews", reviews_api.ReviewViewSet, basename="review")
router.register("seller/products", products_api.SellerProductViewSet, basename="seller-product")
router.register("seller/orders", orders_api.SellerOrderViewSet, basename="seller-order")

admin_router = DefaultRouter()
admin_router.register("products", products_api.AdminProductViewSet, basename="admin-product")
admin_router.register("categories", products_api.AdminCategoryViewSet, basename="admin-category")
admin_router.register("collections", products_api.AdminCollectionViewSet, basename="admin-collection")
admin_router.register("makers", products_api.AdminMakerViewSet, basename="admin-maker")
admin_router.register("orders", orders_api.AdminOrderViewSet, basename="admin-order")
admin_router.register("journal", content_api.AdminArticleViewSet, basename="admin-article")
admin_router.register("faqs", content_api.AdminFAQViewSet, basename="admin-faq")
admin_router.register("contact", content_api.AdminContactViewSet, basename="admin-contact")

urlpatterns = [
    path("health/", health, name="api-health"),
    path("recommendations/", include("recommendations.urls")),
    path("conversations/", include("messaging.urls")),

    # Auth
    path("auth/register/", accounts_api.RegisterView.as_view(), name="api-register"),
    path("auth/login/", accounts_api.LoginView.as_view(), name="api-login"),
    path("auth/logout/", accounts_api.LogoutView.as_view(), name="api-logout"),
    path("auth/me/", accounts_api.MeView.as_view(), name="api-me"),
    path("auth/change-password/", accounts_api.ChangePasswordView.as_view(), name="api-change-password"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="api-token-refresh"),
    path("auth/token/verify/", TokenVerifyView.as_view(), name="api-token-verify"),

    # Wishlist add/remove by product slug
    path("wishlist/<slug:slug>/", accounts_api.wishlist_add, name="api-wishlist-add"),
    path("wishlist/<slug:slug>/remove/", accounts_api.wishlist_remove, name="api-wishlist-remove"),

    # Cart
    path("cart/", orders_api.CartView.as_view(), name="api-cart"),
    path("cart/items/", orders_api.CartItemsView.as_view(), name="api-cart-items"),
    path("cart/items/<int:item_id>/", orders_api.CartItemDetailView.as_view(), name="api-cart-item"),

    # Checkout & payments
    path("checkout/", orders_api.CheckoutView.as_view(), name="api-checkout"),
    path("payments/webhook/", PaymentWebhookView.as_view(), name="api-payment-webhook"),

    # Forms
    path("newsletter/subscribe/", content_api.NewsletterSubscribeView.as_view(), name="api-newsletter"),
    path("contact/", content_api.ContactView.as_view(), name="api-contact"),

    # OpenAPI
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    path("admin/", include((admin_router.urls, "admin-api"))),
    path("", include(router.urls)),
]
