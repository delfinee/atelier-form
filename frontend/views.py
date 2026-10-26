"""Storefront views.

Presentation only: every view reads through `frontend.services` (catalogue and
editorial) or the app models (accounts, orders) and renders a template. Cart
mutation, checkout and wishlist writes all go through the JSON API under /api/,
so there is exactly one implementation of that logic.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta
from urllib.parse import urlsplit

from django.db.models import Avg, Count, Sum
from django.utils import timezone

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _, pgettext
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.models import Address, WishlistItem
from content.models import FAQGroup, NewsletterSubscriber
from orders.models import (
    FulfillmentStatus, Order, OrderItem, OrderStatus, PaymentStatus, SellerFulfillment, ZERO,
)
from orders.services import get_cart, merge_session_cart, update_seller_fulfillment
from payments.models import Payment, PaymentProviderChoices
from payments.services import MockPaymentProvider
from reviews.models import Review
from reviews.errors import is_duplicate_review_error
from recommendations.services import record_product_view

from . import services
from .forms import ProfileForm, RegistrationForm, SellerFulfillmentForm
from .review_forms import ReviewForm
from .mockdata.content import CARE_PAGE, PROCESS_STEPS, SHIPPING_PAGE, SITE, STORY_PAGE

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


# -- Home ----------------------------------------------------------------

def home(request):
    return render(request, "frontend/home.html", {
        "categories": services.categories(),
        "new_arrivals": services.new_arrivals(8),
        "process_steps": PROCESS_STEPS,
        "featured_collection": services.get_collection("earth"),
        "featured_collection_products": services.products_in_collection("earth")[:3],
        "makers": services.all_makers()[:2],
        "gallery": [f"gallery-{i}" for i in range(1, 7)],
        "meta_title": f"{SITE['brand']} — {SITE['tagline']}",
    })


# -- Shop & collections --------------------------------------------------

def _selected_filters(request) -> dict:
    return {
        "categories": request.GET.getlist("category"),
        "materials": request.GET.getlist("material"),
        "colours": request.GET.getlist("colour"),
        "price_bands": request.GET.getlist("price"),
        "availability": request.GET.getlist("availability"),
    }


def shop(request):
    selected = _selected_filters(request)
    sort = request.GET.get("sort", "featured")
    if sort not in dict(services.SORT_OPTIONS):
        sort = "featured"

    products = services.filter_products(**selected, sort=sort)
    active_count = sum(len(v) for v in selected.values())

    return render(request, "frontend/shop/shop.html", {
        "products": products,
        "facets": services.shop_facets(),
        "selected": selected,
        "active_filter_count": active_count,
        "sort": sort,
        "sort_options": services.localized_sort_options(),
        "meta_title": f"{_('Shop')} — {SITE['brand']}",
    })


def collections_index(request):
    return render(request, "frontend/shop/collections.html", {
        "collections": services.all_collections(),
        "meta_title": f"{_('Collections')} — {SITE['brand']}",
    })


def collection_detail(request, slug):
    collection = services.get_collection(slug)
    if not collection:
        raise Http404("Unknown collection")

    sort = request.GET.get("sort", "featured")
    if sort not in dict(services.SORT_OPTIONS):
        sort = "featured"

    return render(request, "frontend/shop/collection_detail.html", {
        "collection": collection,
        "products": services.products_in_collection(slug, sort=sort),
        "sort": sort,
        "sort_options": services.localized_sort_options(),
        "meta_title": f"{collection.title} — {SITE['brand']}",
    })


# -- Product -------------------------------------------------------------

def product_detail(request, slug):
    product = services.get_product(slug)
    if not product:
        raise Http404("Unknown product")

    record_product_view(request, product)

    review_state = "login_required"
    order_item = None
    if request.user.is_authenticated:
        order_item = (OrderItem.objects.filter(
            order__user=request.user, order__payment_status="paid", product=product,
        ).order_by("-order__placed_at").first())
        if Review.objects.filter(user=request.user, product=product).exists():
            review_state = "already_reviewed"
        else:
            review_state = "eligible" if order_item else "purchase_required"

    review_form = ReviewForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if review_state == "login_required":
            return redirect_to_login(request.path)
        if review_state != "eligible":
            messages.error(request, _("You have already reviewed this product.")
                           if review_state == "already_reviewed" else
                           _("Only verified buyers can review this product."))
            return redirect("product_detail", slug=product.slug)
        if review_form.is_valid():
            try:
                with transaction.atomic():
                    Review.objects.create(
                        user=request.user, product=product, order_item=order_item,
                        **review_form.cleaned_data,
                    )
            except IntegrityError as exc:
                if not is_duplicate_review_error(exc):
                    raise
                messages.error(request, _("You have already reviewed this product."))
            else:
                messages.success(request, _("Thank you for reviewing this piece."))
            return redirect("product_detail", slug=product.slug)

    reviews = getattr(product, "reviews").filter(is_published=True).select_related("user")

    return render(request, "frontend/product/detail.html", {
        "product": product,
        "maker": services.get_maker(product.maker.slug),
        "related": services.related_products(product),
        "reviews": reviews,
        "can_review": review_state == "eligible",
        "review_state": review_state,
        "review_form": review_form,
        "in_wishlist": (request.user.is_authenticated and
                        WishlistItem.objects.filter(user=request.user, product=product).exists()),
        "meta_title": f"{product.name} — {SITE['brand']}",
    })


# -- Search --------------------------------------------------------------

def search(request):
    query = request.GET.get("q", "")
    results = services.search(query)
    total = sum(len(v) for v in results.values())
    return render(request, "frontend/search/results.html", {
        "query": query,
        "results": results,
        "total": total,
        "popular": services.POPULAR_SEARCHES,
        "meta_title": f"{_('Search')} — {SITE['brand']}",
    })


@require_GET
def search_api(request):
    """Live results for the search overlay."""
    results = services.search(request.GET.get("q", ""))
    return JsonResponse({
        "products": [
            {"slug": p.slug, "name": p.name, "label": p.short_description,
             "price": float(p.price), "url": f"/products/{p.slug}/",
             "image": p.product_images.all()[0].url if p.product_images.all() else ""}
            for p in results["products"][:5]
        ],
        "collections": [{"title": c.title, "url": f"/collections/{c.slug}/"}
                        for c in results["collections"][:3]],
        "makers": [{"name": m.name, "discipline": m.discipline,
                    "url": f"/makers/{m.slug}/"} for m in results["makers"][:3]],
        "articles": [{"title": a.title, "url": f"/journal/{a.slug}/"}
                     for a in results["articles"][:3]],
    })


@require_GET
def catalogue_api(request):
    """Product lookup table for wishlist and recently-viewed rendering."""
    return JsonResponse(services.catalogue_payload())


# -- Cart & checkout -----------------------------------------------------

def cart(request):
    """The bag page. Lines are fetched from /api/cart/ by the JS layer."""
    return render(request, "frontend/cart.html", {"meta_title": f"{_('Bag')} — {SITE['brand']}"})


def checkout(request):
    cart_obj = get_cart(request, create=False)
    addresses = (Address.objects.filter(user=request.user)
                 if request.user.is_authenticated else Address.objects.none())
    return render(request, "frontend/checkout.html", {
        "addresses": addresses,
        "customer": request.user if request.user.is_authenticated else None,
        "has_items": bool(cart_obj and getattr(cart_obj, "items").exists()),
        "meta_title": f"{_('Checkout')} — {SITE['brand']}",
    })


@require_http_methods(["GET", "POST"])
def mock_payment(request, uuid):
    """Interactive, no-money payment simulator for demos and local testing."""
    payment = get_object_or_404(
        Payment.objects.select_related("order"),
        uuid=uuid,
        provider=PaymentProviderChoices.MOCK,
    )
    order = payment.order
    order_user_id = getattr(order, "user_id", None)
    if order_user_id and (not request.user.is_authenticated or order_user_id != request.user.id):
        raise Http404("Unknown payment")

    if request.method == "POST":
        succeed = request.POST.get("result") == "succeeded"
        MockPaymentProvider().confirm(payment, succeed=succeed)
        return redirect("order_confirmation", uuid=order.uuid)

    return render(request, "frontend/mock_payment.html", {
        "payment": payment,
        "order": order,
        "meta_title": f"{_('Sandbox payment')} — {SITE['brand']}",
    })


def order_confirmation(request, uuid):
    """Shown after checkout. Readable by the buyer, or by anyone holding the
    order's unguessable UUID -- which is how a guest sees their own order."""
    order = get_object_or_404(Order.objects.prefetch_related("items"), uuid=uuid)
    order_user_id = getattr(order, "user_id", None)
    if order_user_id and (not request.user.is_authenticated or order_user_id != request.user.id):
        raise Http404("Unknown order")
    return render(request, "frontend/order_confirmation.html", {
        "order": order,
        "meta_title": f"{_('Order %(number)s') % {'number': order.order_number}} — {SITE['brand']}",
    })


# -- Account & auth ------------------------------------------------------

# Everything the buyer progress tag reads (frontend.order_progress), loaded
# once per page rather than once per order.
BUYER_ORDER_PREFETCH = ("items", "seller_fulfillments__maker")


@login_required
def account_overview(request):
    orders = Order.objects.filter(user=request.user).prefetch_related(*BUYER_ORDER_PREFETCH)
    return render(request, "frontend/account/overview.html", {
        "customer": request.user,
        "recent_order": orders.first(),
        "order_count": orders.count(),
        "address_count": request.user.addresses.count(),
        "wishlist_count": WishlistItem.objects.filter(user=request.user).count(),
        "meta_title": f"{_('Account')} — {SITE['brand']}",
    })


@login_required
def account_orders(request):
    return render(request, "frontend/account/orders.html", {
        "customer": request.user,
        "orders": Order.objects.filter(user=request.user).prefetch_related(*BUYER_ORDER_PREFETCH),
        "meta_title": f"{_('Orders')} — {SITE['brand']}",
    })


@login_required
def account_order_detail(request, order_id):
    # Scoped to the signed-in user: another customer's order number 404s.
    order = Order.objects.filter(user=request.user, order_number=order_id) \
        .prefetch_related(*BUYER_ORDER_PREFETCH).first()
    if not order:
        raise Http404("Unknown order")
    return render(request, "frontend/account/order_detail.html", {
        "customer": request.user, "order": order,
        "current_path": reverse("account_orders"),
        "meta_title": f"{_('Order %(number)s') % {'number': order.order_number}} — {SITE['brand']}",
    })


def _render_account_profile(request, password_form=None, profile_form=None):
    return render(request, "frontend/account/profile.html", {
        "customer": request.user, "meta_title": f"{_('Profile')} — {SITE['brand']}",
        "current_path": reverse("account_profile"),
        "profile_form": (profile_form if profile_form is not None
                         else ProfileForm(user=request.user)),
        "password_form": (password_form if password_form is not None
                          else PasswordChangeForm(request.user)),
    })


@login_required
def account_profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Your details have been saved."))
            return redirect("account_profile")
        return _render_account_profile(request, profile_form=form)

    return _render_account_profile(request)


@require_POST
def account_change_password(request):
    if not request.user.is_authenticated:
        # Login must return to the form, not GET this POST-only action.
        return redirect_to_login(reverse("account_profile"))
    form = PasswordChangeForm(request.user, request.POST)
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, _("Your password has been changed."))
        return redirect("account_profile")
    return _render_account_profile(request, password_form=form)


@login_required
def account_addresses(request):
    if request.method == "POST":
        Address.objects.create(
            user=request.user,
            label=request.POST.get("label", "Home").strip() or "Home",
            first_name=request.POST.get("first_name", "").strip(),
            last_name=request.POST.get("last_name", "").strip(),
            address_line_1=request.POST.get("address_line_1", "").strip(),
            address_line_2=request.POST.get("address_line_2", "").strip(),
            city=request.POST.get("city", "").strip(),
            postal_code=request.POST.get("postal_code", "").strip(),
            country=request.POST.get("country", "China").strip(),
            phone=request.POST.get("phone", "").strip(),
            is_default=bool(request.POST.get("is_default")),
        )
        messages.success(request, _("Address saved."))
        return redirect("account_addresses")

    return render(request, "frontend/account/addresses.html", {
        "customer": request.user,
        "addresses": request.user.addresses.all(),
        "meta_title": f"{_('Addresses')} — {SITE['brand']}",
    })


@login_required
@require_POST
def account_address_delete(request, uuid):
    deleted, _details = Address.objects.filter(user=request.user, uuid=uuid).delete()
    message = _("Address removed.") if deleted else _("That address no longer exists.")
    messages.success(request, message)
    return redirect("account_addresses")


@login_required
def account_wishlist(request):
    items = (WishlistItem.objects.filter(user=request.user)
             .select_related("product", "product__category", "product__maker")
             .prefetch_related("product__product_images"))
    return render(request, "frontend/account/wishlist.html", {
        "customer": request.user,
        "wishlist_products": [services.localize_product(item.product) for item in items],
        "meta_title": f"{_('Wishlist')} — {SITE['brand']}",
    })


def auth_page(request, mode):
    """Sign in and register.

    Uses Django's session authentication -- the frontend is server-rendered,
    so a session cookie is the right mechanism. The JWT endpoints under
    /api/auth/ exist for non-browser clients.
    """
    titles = {"login": _("Sign in"), "register": _("Create an account")}
    if request.user.is_authenticated and mode in {"login", "register"}:
        return redirect("account_overview")

    errors: dict[str, str] = {}
    values: dict[str, str] = {}
    registration_form = (
        RegistrationForm(request.POST if request.method == "POST" else None)
        if mode == "register" else None
    )

    if request.method == "POST":
        values = {k: v.strip() for k, v in request.POST.items() if k != "password"}
        if mode == "login":
            email = request.POST.get("email", "").strip().lower()
            password = request.POST.get("password", "")
            user = authenticate(request, username=email, password=password)
            if user is None:
                # One message for every failure: this must not reveal whether
                # an account exists.
                errors["form"] = _("Invalid email or password.")
            else:
                merge_session_cart(request, user)      # keep the guest's bag
                login(request, user)
                name = user.first_name or pgettext("account welcome fallback", "there")
                messages.success(request, _("Welcome back, %(name)s.") % {"name": name})
                next_url = request.GET.get("next", "").strip()
                if (url_has_allowed_host_and_scheme(
                    next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
                ) and urlsplit(next_url).path.startswith("/")):
                    return redirect(next_url)
                return redirect("account_overview")

        elif mode == "register" and registration_form is not None:
            if registration_form.is_valid():
                user = registration_form.save()
                merge_session_cart(request, user)
                login(request, user)
                messages.success(request, _("Your account is ready."))
                return redirect("account_overview")
            errors = {field: " ".join(field_errors)
                      for field, field_errors in registration_form.errors.items()}

    return render(request, "frontend/account/auth.html", {
        "mode": mode, "heading": titles[mode], "errors": errors, "values": values,
        "registration_form": registration_form,
        "meta_title": f"{titles[mode]} — {SITE['brand']}",
    })


@require_POST
def account_logout(request):
    logout(request)
    messages.success(request, _("You have been signed out."))
    return redirect("home")


@login_required
def seller_dashboard(request):
    if not request.user.is_seller or not hasattr(request.user, "maker_profile"):
        raise PermissionDenied("A linked seller profile is required.")
    maker = request.user.maker_profile

    # ------------------------------------------------------------------
    # Time period selector — driven by ?period= query param
    # Defaults to "30d" (last 30 days) if nothing is specified.
    # ------------------------------------------------------------------
    PERIOD_OPTIONS = {
        "24h":  ("Last 24 Hours",   timedelta(hours=24)),
        "7d":   ("Last 7 Days",     timedelta(days=7)),
        "30d":  ("Last 30 Days",    timedelta(days=30)),
        "all":  ("All Time",        None),
    }
    period_key = request.GET.get("period", "30d")
    if period_key not in PERIOD_OPTIONS:
        period_key = "30d"
    period_label, period_delta = PERIOD_OPTIONS[period_key]

    # Base queryset: paid order lines belonging to this seller.
    # This is the source of truth for all financial and volume metrics.
    paid_items_qs = (
        OrderItem.objects
        .filter(maker=maker, order__payment_status=PaymentStatus.PAID)
    )

    # Apply the time window filter if a bounded period is selected.
    if period_delta is not None:
        since = timezone.now() - period_delta
        paid_items_qs = paid_items_qs.filter(order__placed_at__gte=since)

    # ------------------------------------------------------------------
    # Core metric 1 — Revenue, Units Sold, and Order Count
    # Sum() and Count() from Django ORM aggregations do the math for us.
    # ------------------------------------------------------------------
    totals = paid_items_qs.aggregate(
        revenue=Sum("line_total"),         # e.g. Decimal("8450.00")
        units_sold=Sum("quantity"),        # e.g. 34
        order_count=Count("order", distinct=True),  # e.g. 19 unique orders
    )
    total_revenue = totals["revenue"] or 0
    total_units = totals["units_sold"] or 0
    total_orders = totals["order_count"] or 0
    # Average order value: seller revenue / distinct paid orders containing
    # this seller. No paid orders yet is not an error -- it's a real,
    # displayable zero, not a ZeroDivisionError.
    average_order_value = (total_revenue / total_orders) if total_orders else ZERO

    # ------------------------------------------------------------------
    # Core metric 2 — Customer Favorites (Wishlist Likes)
    # Count how many times any customer has saved this maker's products.
    # ------------------------------------------------------------------
    total_wishlist_saves = (
        WishlistItem.objects
        .filter(product__maker=maker)
        .count()
    )

    # ------------------------------------------------------------------
    # Core metric 3 — Average Star Rating from published reviews
    # ------------------------------------------------------------------
    rating_data = (
        Review.objects
        .filter(product__maker=maker, is_published=True)
        .aggregate(
            avg_rating=Avg("rating"),
            review_count=Count("id"),
        )
    )
    avg_rating = rating_data["avg_rating"]       # float or None if no reviews yet
    review_count = rating_data["review_count"]   # int

    # ------------------------------------------------------------------
    # Core metric 4 — Pending Dispatches (orders awaiting shipment)
    # SellerFulfillment rows are created at checkout, before payment is
    # confirmed (see orders.services.create_order), so an unfulfilled row
    # alone does not mean "ready to pack" -- it may belong to an order that
    # was never paid, or whose payment failed. "Awaiting dispatch" means the
    # seller was actually paid and still hasn't shipped their part.
    #
    # A paid order can still end up CANCELLED (e.g. an admin cancels it
    # after payment, ahead of any refund) -- excluded explicitly, since a
    # cancelled order has nothing left to pack regardless of payment state.
    # ------------------------------------------------------------------
    pending_dispatch_count = (
        SellerFulfillment.objects
        .filter(maker=maker, status=FulfillmentStatus.UNFULFILLED,
               order__payment_status=PaymentStatus.PAID)
        .exclude(order__status=OrderStatus.CANCELLED)
        .count()
    )

    # ------------------------------------------------------------------
    # Best-selling products — top 5 ranked by revenue, with wishlist
    # counts merged in from a separate query.
    #
    # wishlist_saves cannot be annotated in the same query as units/revenue:
    # joining OrderItem to WishlistItem through product fans out the row
    # count (N order-item rows x M wishlist rows for that product), which
    # inflates Sum("quantity")/Sum("line_total") by a factor of M even
    # though Count(..., distinct=True) itself stays correct. Verified
    # directly: 5 units / $50.00 across 2 order-item rows and 4 wishlist
    # rows for one product was returning 20 units / $200.00 with a single
    # annotate() call.
    # ------------------------------------------------------------------
    best_sellers = list(
        paid_items_qs
        .values("product_id", "product_name")
        .annotate(units=Sum("quantity"), revenue=Sum("line_total"))
        .order_by("-revenue")[:5]
    )
    wishlist_counts = dict(
        WishlistItem.objects
        .filter(product_id__in=[row["product_id"] for row in best_sellers])
        .values("product_id")
        .annotate(count=Count("id"))
        .values_list("product_id", "count")
    )
    for row in best_sellers:
        row["wishlist_saves"] = wishlist_counts.get(row["product_id"], 0)

    # ------------------------------------------------------------------
    # Low Stock Alerts — active variants at or below the project's
    # configured low-stock threshold (settings.COMMERCE["LOW_STOCK_THRESHOLD"]),
    # but not sold out. `product_variants` is the actual reverse accessor
    # from Product to ProductVariant (see products.models.ProductVariant);
    # the `variants` property on Product is a plain Python list and cannot
    # be used inside a queryset filter/prefetch.
    #
    # Restricted to `product_variants__is_active=True`: an inactive variant
    # is deliberately not offered for sale, so its stock level isn't
    # something the seller needs to restock. Made-to-order products are
    # excluded entirely: per orders.services._available_for, stock checks
    # never apply to them (is_made_to_order bypasses the stock_quantity
    # check at checkout), so a low numeric stock_quantity on one of their
    # variants doesn't mean anything is actually running out.
    # ------------------------------------------------------------------
    low_stock_threshold = settings.COMMERCE["LOW_STOCK_THRESHOLD"]
    low_stock_products = (
        maker.products
        .filter(is_made_to_order=False,
               product_variants__is_active=True,
               product_variants__stock_quantity__lte=low_stock_threshold,
               product_variants__stock_quantity__gt=0)
        .distinct()
        .prefetch_related("product_variants")[:10]
    )

    # Recent incoming order lines (unchanged from original dashboard)
    seller_items = (
        OrderItem.objects
        .filter(maker=maker)
        .select_related("order", "product")
        .order_by("-order__placed_at")[:50]
    )

    return render(request, "frontend/seller/dashboard.html", {
        "maker": maker,
        "products": maker.products.all().order_by("-updated_at"),
        "seller_items": seller_items,
        "meta_title": f"Seller dashboard — {SITE['brand']}",
        # Time period context
        "period_key": period_key,
        "period_label": period_label,
        "period_options": PERIOD_OPTIONS,
        # Analytics metrics
        "total_revenue": total_revenue,
        "total_units": total_units,
        "total_orders": total_orders,
        "average_order_value": average_order_value,
        "total_wishlist_saves": total_wishlist_saves,
        "avg_rating": avg_rating,
        "review_count": review_count,
        "pending_dispatch_count": pending_dispatch_count,
        "best_sellers": best_sellers,
        "low_stock_products": low_stock_products,
    })


@login_required
@require_http_methods(["GET", "POST"])
def seller_order_detail(request, order_number):
    if not request.user.is_seller or not hasattr(request.user, "maker_profile"):
        raise PermissionDenied("A linked seller profile is required.")
    maker = request.user.maker_profile

    # Scoped in the query itself: an order with none of this seller's lines 404s,
    # exactly as GET /api/seller/orders/<uuid>/ does.
    order = get_object_or_404(
        Order.objects.filter(items__maker=maker).distinct(), order_number=order_number)
    items = order.items.filter(maker=maker)
    # Never created or synthesised here. A seller-owned order with no row
    # (legacy data) stays readable but not editable, matching the API, whose
    # fulfilment PATCH 404s without the seller's own row.
    fulfillment = order.seller_fulfillments.filter(maker=maker).first()

    if request.method == "POST":
        if fulfillment is None:
            raise Http404("No fulfilment record for this seller.")
        form = SellerFulfillmentForm(request.POST)
        if form.is_valid():
            # Ownership, dispatch eligibility, shipped_at and the parent status
            # sync all live in the service; a rule it rejects is shown on the form.
            try:
                update_seller_fulfillment(fulfillment, acting_maker=maker, **form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, _("Fulfilment updated."))
                return redirect("seller_order_detail", order_number=order.order_number)
    elif fulfillment is not None:
        form = SellerFulfillmentForm(initial={
            "status": fulfillment.status,
            "carrier": fulfillment.carrier,
            "tracking_number": fulfillment.tracking_number,
        })
    else:
        form = None

    return render(request, "frontend/seller/order_detail.html", {
        "maker": maker,
        "order": order,
        "items": items,
        "seller_subtotal": sum((item.line_total for item in items), ZERO),
        "fulfillment": fulfillment,
        "form": form,
        "meta_title": f"Order {order.order_number} — {SITE['brand']}",
    })


@login_required
def seller_messages_inbox(request):
    from products.models import Maker
    maker = getattr(request.user, "maker_profile", None)
    if not maker:
        maker = Maker.objects.filter(owner=request.user).first()
    if not maker:
        raise PermissionDenied("A linked seller profile is required.")
    from messaging.models import Conversation
    conversations = (
        Conversation.objects.filter(maker=maker)
        .select_related("buyer", "product", "order")
        .prefetch_related("messages", "messages__sender")
        .order_by("-updated_at")
    )
    return render(request, "frontend/seller/messages_inbox.html", {
        "maker": maker,
        "conversations": conversations,
        "meta_title": f"Customer Inquiries — {SITE['brand']}",
    })


@login_required
def seller_message_thread(request, conversation_uuid):
    from products.models import Maker
    maker = getattr(request.user, "maker_profile", None)
    if not maker:
        maker = Maker.objects.filter(owner=request.user).first()
    if not maker:
        raise PermissionDenied("A linked seller profile is required.")
    from messaging.models import Conversation
    from messaging import services as messaging_services
    conversation = get_object_or_404(
        Conversation.objects.select_related("buyer", "maker", "product", "order"),
        maker=maker,
        uuid=conversation_uuid,
    )
    if request.method == "POST":
        body = (request.POST.get("body") or "").strip()
        if body:
            msg = messaging_services.send_message(conversation, request.user, body)
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", ""):
                return JsonResponse({
                    "uuid": str(msg.uuid),
                    "body": msg.body,
                    "created_at": msg.created_at.isoformat(),
                    "sender_id": msg.sender_id,
                    "is_sender": True,
                    "sender_name": request.user.get_full_name() or request.user.email.split("@")[0],
                }, status=201)
            messages.success(request, _("Reply sent."))
            return redirect("seller_message_thread", conversation_uuid=conversation.uuid)

    messaging_services.mark_messages_read(conversation, request.user)
    thread_messages = conversation.messages.select_related("sender").order_by("created_at")
    return render(request, "frontend/seller/message_thread.html", {
        "maker": maker,
        "conversation": conversation,
        "messages_list": thread_messages,
        "meta_title": f"Inquiry from {conversation.buyer.get_full_name() or conversation.buyer.email} — {SITE['brand']}",
    })


# -- Editorial & informational -------------------------------------------

def our_story(request):
    return render(request, "frontend/pages/our_story.html", {
        "page": STORY_PAGE, "makers": services.all_makers(),
        "process_steps": PROCESS_STEPS,
        "meta_title": f"{_('Our Story')} — {SITE['brand']}",
    })


def makers_index(request):
    return render(request, "frontend/makers/index.html", {
        "makers": services.all_makers(),
        "meta_title": f"{_('Makers')} — {SITE['brand']}",
    })


def maker_detail(request, slug):
    maker = services.get_maker(slug)
    if not maker:
        raise Http404("Unknown maker")
    return render(request, "frontend/makers/detail.html", {
        "maker": maker, "products": services.products_by_maker(slug),
        "meta_title": f"{maker.name} — {SITE['brand']}",
    })


def journal_index(request):
    articles = services.all_articles()
    return render(request, "frontend/journal/index.html", {
        "lead": articles[0] if articles else None,
        "articles": articles[1:],
        "meta_title": f"{_('Journal')} — {SITE['brand']}",
    })


def journal_detail(request, slug):
    article = services.get_article(slug)
    if not article:
        raise Http404("Unknown article")
    return render(request, "frontend/journal/detail.html", {
        "article": article, "related": services.related_articles(article),
        "meta_title": f"{article.title} — {SITE['brand']}",
    })


def _faq_groups():
    from .catalogue_i18n import localize_faq_group
    return [localize_faq_group(group) for group in
            FAQGroup.objects.filter(is_active=True).prefetch_related("faqs")]


def contact(request):
    return render(request, "frontend/pages/contact.html", {
        "faq_groups": _faq_groups()[:3],
        "meta_title": f"{_('Contact')} — {SITE['brand']}",
    })


def faq(request):
    return render(request, "frontend/pages/faq.html", {
        "faq_groups": _faq_groups(), "meta_title": f"{_('FAQ')} — {SITE['brand']}",
    })


def shipping_returns(request):
    return render(request, "frontend/pages/longform.html", {
        "page": SHIPPING_PAGE,
        "meta_title": f"{_('Shipping & Returns')} — {SITE['brand']}",
    })


def care_guide(request):
    return render(request, "frontend/pages/care.html", {
        "page": CARE_PAGE, "meta_title": f"{_('Care Guide')} — {SITE['brand']}",
    })


def legal(request, slug):
    titles = {"privacy": _("Privacy Policy"), "terms": _("Terms of Service")}
    return render(request, "frontend/pages/legal.html", {
        "title": titles[slug], "slug": slug,
        "meta_title": f"{titles[slug]} — {SITE['brand']}",
    })


# -- Newsletter ----------------------------------------------------------

@require_POST
def newsletter_signup(request):
    """Kept at its original path for the existing JS. Writes a real subscriber."""
    try:
        email = json.loads(request.body or "{}").get("email", "")
    except json.JSONDecodeError:
        email = ""
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        return JsonResponse({"ok": False, "error": _("Enter a valid email address.")}, status=400)

    subscriber = NewsletterSubscriber.objects.filter(email=email).first()
    if subscriber:
        if not subscriber.is_active:
            subscriber.resubscribe()
    else:
        NewsletterSubscriber.objects.create(email=email)

    # Identical response either way: never disclose who is already subscribed.
    return JsonResponse({
        "ok": True,
        "message": _("You're on the list. Look out for the next note."),
    })


