"""Storefront views.

Presentation only: every view reads through `frontend.services` (catalogue and
editorial) or the app models (accounts, orders) and renders a template. Cart
mutation, checkout and wishlist writes all go through the JSON API under /api/,
so there is exactly one implementation of that logic.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.models import Address, WishlistItem
from content.models import FAQGroup, NewsletterSubscriber
from orders.models import Order, OrderItem
from orders.services import get_cart, merge_session_cart
from payments.models import Payment, PaymentProviderChoices
from payments.services import MockPaymentProvider
from reviews.models import Review

from . import services
from .forms import RegistrationForm
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
        "sort_options": services.SORT_OPTIONS,
        "meta_title": f"Shop — {SITE['brand']}",
    })


def collections_index(request):
    return render(request, "frontend/shop/collections.html", {
        "collections": services.all_collections(),
        "meta_title": f"Collections — {SITE['brand']}",
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
        "sort_options": services.SORT_OPTIONS,
        "meta_title": f"{collection.title} — {SITE['brand']}",
    })


# -- Product -------------------------------------------------------------

def product_detail(request, slug):
    product = services.get_product(slug)
    if not product:
        raise Http404("Unknown product")

    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect(f"/account/login/?next=/products/{product.slug}/")
        order_item = (OrderItem.objects.filter(
            order__user=request.user, order__payment_status="paid", product=product,
        ).order_by("-order__placed_at").first())
        if order_item is None:
            messages.error(request, "Only verified buyers can review this product.")
        elif Review.objects.filter(user=request.user, product=product).exists():
            messages.error(request, "You have already reviewed this product.")
        else:
            try:
                rating = int(request.POST.get("rating", ""))
                if rating not in range(1, 6):
                    raise ValueError
                Review.objects.create(
                    user=request.user, product=product, order_item=order_item,
                    rating=rating, title=request.POST.get("title", "").strip()[:160],
                    body=request.POST.get("body", "").strip(),
                )
                messages.success(request, "Thank you for reviewing this piece.")
            except ValueError:
                messages.error(request, "Choose a rating from 1 to 5.")
        return redirect("product_detail", slug=product.slug)

    reviews = getattr(product, "reviews").filter(is_published=True).select_related("user")
    can_review = False
    if request.user.is_authenticated:
        can_review = (not reviews.filter(user=request.user).exists() and
                      OrderItem.objects.filter(order__user=request.user,
                                               order__payment_status="paid",
                                               product=product).exists())

    return render(request, "frontend/product/detail.html", {
        "product": product,
        "maker": product.maker,
        "related": services.related_products(product),
        "reviews": reviews,
        "can_review": can_review,
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
        "meta_title": f"Search — {SITE['brand']}",
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
    return render(request, "frontend/cart.html", {"meta_title": f"Bag — {SITE['brand']}"})


def checkout(request):
    cart_obj = get_cart(request, create=False)
    addresses = (Address.objects.filter(user=request.user)
                 if request.user.is_authenticated else Address.objects.none())
    return render(request, "frontend/checkout.html", {
        "addresses": addresses,
        "customer": request.user if request.user.is_authenticated else None,
        "has_items": bool(cart_obj and getattr(cart_obj, "items").exists()),
        "meta_title": f"Checkout — {SITE['brand']}",
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
        "meta_title": f"Sandbox payment — {SITE['brand']}",
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
        "meta_title": f"Order {order.order_number} — {SITE['brand']}",
    })


# -- Account & auth ------------------------------------------------------

@login_required
def account_overview(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items")
    return render(request, "frontend/account/overview.html", {
        "customer": request.user,
        "recent_order": orders.first(),
        "order_count": orders.count(),
        "address_count": request.user.addresses.count(),
        "wishlist_count": WishlistItem.objects.filter(user=request.user).count(),
        "meta_title": f"Account — {SITE['brand']}",
    })


@login_required
def account_orders(request):
    return render(request, "frontend/account/orders.html", {
        "customer": request.user,
        "orders": Order.objects.filter(user=request.user).prefetch_related("items"),
        "meta_title": f"Orders — {SITE['brand']}",
    })


@login_required
def account_order_detail(request, order_id):
    # Scoped to the signed-in user: another customer's order number 404s.
    order = Order.objects.filter(user=request.user, order_number=order_id) \
        .prefetch_related("items").first()
    if not order:
        raise Http404("Unknown order")
    return render(request, "frontend/account/order_detail.html", {
        "customer": request.user, "order": order,
        "meta_title": f"Order {order.order_number} — {SITE['brand']}",
    })


def _render_account_profile(request, password_form=None):
    return render(request, "frontend/account/profile.html", {
        "customer": request.user, "meta_title": f"Profile — {SITE['brand']}",
        "current_path": reverse("account_profile"),
        "password_form": (password_form if password_form is not None
                          else PasswordChangeForm(request.user)),
    })


@login_required
def account_profile(request):
    if request.method == "POST":
        user = request.user
        user.first_name = request.POST.get("first_name", user.first_name).strip()
        user.last_name = request.POST.get("last_name", user.last_name).strip()
        user.phone = request.POST.get("phone", user.phone).strip()
        user.accepts_marketing = bool(request.POST.get("accepts_marketing"))
        user.save(update_fields=["first_name", "last_name", "phone",
                                 "accepts_marketing", "updated_at"])
        messages.success(request, "Your details have been saved.")
        return redirect("account_profile")

    return _render_account_profile(request)


@login_required
@require_POST
def account_change_password(request):
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
        messages.success(request, "Address saved.")
        return redirect("account_addresses")

    return render(request, "frontend/account/addresses.html", {
        "customer": request.user,
        "addresses": request.user.addresses.all(),
        "meta_title": f"Addresses — {SITE['brand']}",
    })


@login_required
@require_POST
def account_address_delete(request, uuid):
    deleted, _ = Address.objects.filter(user=request.user, uuid=uuid).delete()
    messages.success(request, "Address removed." if deleted else "That address no longer exists.")
    return redirect("account_addresses")


@login_required
def account_wishlist(request):
    items = (WishlistItem.objects.filter(user=request.user)
             .select_related("product", "product__category", "product__maker")
             .prefetch_related("product__product_images"))
    return render(request, "frontend/account/wishlist.html", {
        "customer": request.user,
        "wishlist_products": [item.product for item in items],
        "meta_title": f"Wishlist — {SITE['brand']}",
    })


def auth_page(request, mode):
    """Sign in and register.

    Uses Django's session authentication -- the frontend is server-rendered,
    so a session cookie is the right mechanism. The JWT endpoints under
    /api/auth/ exist for non-browser clients.
    """
    titles = {"login": "Sign in", "register": "Create an account"}
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
                errors["form"] = "Invalid email or password."
            else:
                merge_session_cart(request, user)      # keep the guest's bag
                login(request, user)
                messages.success(request, f"Welcome back, {user.first_name or 'there'}.")
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
                messages.success(request, "Your account is ready.")
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
    messages.success(request, "You have been signed out.")
    return redirect("home")


@login_required
def seller_dashboard(request):
    if not request.user.is_seller or not hasattr(request.user, "maker_profile"):
        raise PermissionDenied("A linked seller profile is required.")
    maker = request.user.maker_profile
    seller_items = (OrderItem.objects.filter(maker=maker)
                    .select_related("order", "product").order_by("-order__placed_at"))
    return render(request, "frontend/seller/dashboard.html", {
        "maker": maker,
        "products": maker.products.all().order_by("-updated_at"),
        "seller_items": seller_items[:50],
        "meta_title": f"Seller dashboard — {SITE['brand']}",
    })


# -- Editorial & informational -------------------------------------------

def our_story(request):
    return render(request, "frontend/pages/our_story.html", {
        "page": STORY_PAGE, "makers": services.all_makers(),
        "process_steps": PROCESS_STEPS,
        "meta_title": f"Our Story — {SITE['brand']}",
    })


def makers_index(request):
    return render(request, "frontend/makers/index.html", {
        "makers": services.all_makers(),
        "meta_title": f"Makers — {SITE['brand']}",
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
        "meta_title": f"Journal — {SITE['brand']}",
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
    return FAQGroup.objects.filter(is_active=True).prefetch_related("faqs")


def contact(request):
    return render(request, "frontend/pages/contact.html", {
        "faq_groups": _faq_groups()[:3],
        "meta_title": f"Contact — {SITE['brand']}",
    })


def faq(request):
    return render(request, "frontend/pages/faq.html", {
        "faq_groups": _faq_groups(), "meta_title": f"FAQ — {SITE['brand']}",
    })


def shipping_returns(request):
    return render(request, "frontend/pages/longform.html", {
        "page": SHIPPING_PAGE,
        "meta_title": f"Shipping & Returns — {SITE['brand']}",
    })


def care_guide(request):
    return render(request, "frontend/pages/care.html", {
        "page": CARE_PAGE, "meta_title": f"Care Guide — {SITE['brand']}",
    })


def legal(request, slug):
    titles = {"privacy": "Privacy Policy", "terms": "Terms of Service"}
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
        return JsonResponse({"ok": False, "error": "Enter a valid email address."}, status=400)

    subscriber = NewsletterSubscriber.objects.filter(email=email).first()
    if subscriber:
        if not subscriber.is_active:
            subscriber.resubscribe()
    else:
        NewsletterSubscriber.objects.create(email=email)

    # Identical response either way: never disclose who is already subscribed.
    return JsonResponse({"ok": True, "message": "You're on the list. Look out for the next note."})
