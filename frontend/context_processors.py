"""Values every template needs: brand config, navigation and viewer state."""

from __future__ import annotations

from django.conf import settings
from django.middleware.csrf import get_token
from django.urls import reverse

from accounts.models import WishlistItem

from .mockdata.content import FOOTER_NAV, PRIMARY_NAV, SITE
from .services import POPULAR_SEARCHES


def frontend(request) -> dict:
    user = getattr(request, "user", None)
    authenticated = bool(user is not None and user.is_authenticated)
    site = {
        **SITE,
        "currency_symbol": settings.COMMERCE["CURRENCY_SYMBOL"],
        "free_shipping_threshold": settings.COMMERCE["FREE_SHIPPING_THRESHOLD"],
        "shipping_standard": settings.COMMERCE["SHIPPING_STANDARD"],
        "shipping_express": settings.COMMERCE["SHIPPING_EXPRESS"],
    }

    # Slugs only, so the page can paint the wishlist hearts on first render
    # without a round-trip. The JS layer keeps them in step after that.
    wishlist_slugs: list[str] = []
    if authenticated:
        wishlist_slugs = list(
            WishlistItem.objects.filter(user=user).values_list("product__slug", flat=True)
        )

    return {
        "site": site,
        "primary_nav": PRIMARY_NAV,
        "footer_nav": FOOTER_NAV,
        "popular_searches": POPULAR_SEARCHES,
        "current_path": request.path,
        # Rendered into the page with |json_script -- never hand-built in the
        # template, where autoescaping would corrupt any string it contains.
        "af_config": {
            "currency_symbol": site["currency_symbol"],
            "free_shipping_threshold": site["free_shipping_threshold"],
            "shipping_standard": site["shipping_standard"],
            "shipping_express": site["shipping_express"],
            "csrf": get_token(request),
            "authenticated": authenticated,
            "wishlist": wishlist_slugs,
            "urls": {
                "cart": reverse("api-cart"),
                "cartItems": reverse("api-cart-items"),
                "checkout": reverse("api-checkout"),
                "wishlist": "/api/wishlist/",
                "catalogue": reverse("catalogue_api"),
                "search": reverse("search_api"),
                "newsletter": reverse("newsletter_signup"),
            },
        },
    }
