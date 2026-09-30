"""Seller portal views: product CRUD, variant/image management, and order list."""

from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from orders.models import Order, OrderItem
from products.models import Product
from .forms_seller import SellerImageFormSet, SellerProductForm, SellerVariantFormSet


def _get_seller_maker(request):
    """Enforce seller role and return linked Maker profile."""
    if not request.user.is_authenticated or not getattr(request.user, "is_seller", False) or not hasattr(request.user, "maker_profile"):
        raise PermissionDenied("A linked seller profile is required.")
    return request.user.maker_profile


@login_required
@require_http_methods(["GET"])
def seller_product_list(request):
    """List all products owned by the authenticated seller."""
    maker = _get_seller_maker(request)
    products = (
        maker.products
        .select_related("category")
        .prefetch_related("product_variants", "product_images")
        .order_by("-updated_at")
    )
    return render(request, "frontend/seller/products.html", {
        "maker": maker,
        "products": products,
        "meta_title": f"Products — {maker.name}",
    })


@login_required
@require_http_methods(["GET", "POST"])
def seller_product_create(request):
    """Create a new product with variants and image references."""
    maker = _get_seller_maker(request)

    if request.method == "POST":
        form = SellerProductForm(request.POST)
        variant_formset = SellerVariantFormSet(request.POST)
        image_formset = SellerImageFormSet(request.POST)

        if form.is_valid() and variant_formset.is_valid() and image_formset.is_valid():
            product = form.save(commit=False)
            product.maker = maker

            # Generate unique slug
            base_slug = slugify(product.name)[:170] or "product"
            slug = base_slug
            counter = 1
            while Product.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            product.slug = slug
            product.save()

            variant_formset.instance = product
            variant_formset.save()

            image_formset.instance = product
            image_formset.save()

            product.refresh_stock_status()
            messages.success(request, _(f"Product '{product.name}' was created successfully."))
            return redirect("seller_product_list")
        else:
            messages.error(request, _("Please correct the errors below before saving."))
    else:
        form = SellerProductForm()
        variant_formset = SellerVariantFormSet()
        image_formset = SellerImageFormSet()

    return render(request, "frontend/seller/product_form.html", {
        "maker": maker,
        "form": form,
        "variant_formset": variant_formset,
        "image_formset": image_formset,
        "is_edit": False,
        "meta_title": f"Add New Product — {maker.name}",
    })


@login_required
@require_http_methods(["GET", "POST"])
def seller_product_edit(request, slug):
    """Edit an existing seller product and its variants/images."""
    maker = _get_seller_maker(request)
    product = get_object_or_404(maker.products, slug=slug)

    if request.method == "POST":
        form = SellerProductForm(request.POST, instance=product)
        variant_formset = SellerVariantFormSet(request.POST, instance=product)
        image_formset = SellerImageFormSet(request.POST, instance=product)

        if form.is_valid() and variant_formset.is_valid() and image_formset.is_valid():
            product = form.save()
            variant_formset.save()
            image_formset.save()
            product.refresh_stock_status()
            messages.success(request, _(f"Product '{product.name}' was updated successfully."))
            return redirect("seller_product_list")
        else:
            messages.error(request, _("Please correct the errors below before saving."))
    else:
        form = SellerProductForm(instance=product)
        variant_formset = SellerVariantFormSet(instance=product)
        image_formset = SellerImageFormSet(instance=product)

    return render(request, "frontend/seller/product_form.html", {
        "maker": maker,
        "product": product,
        "form": form,
        "variant_formset": variant_formset,
        "image_formset": image_formset,
        "is_edit": True,
        "meta_title": f"Edit {product.name} — {maker.name}",
    })


@login_required
@require_http_methods(["GET"])
def seller_order_list(request):
    """Display all customer orders containing items from this seller."""
    maker = _get_seller_maker(request)
    order_ids = (
        OrderItem.objects.filter(maker=maker)
        .order_by()
        .values_list("order_id", flat=True)
        .distinct()
    )
    orders = (
        Order.objects.filter(id__in=order_ids)
        .select_related("user")
        .prefetch_related("items", "seller_fulfillments")
        .order_by("-placed_at")
    )

    seller_orders = []
    for order in orders:
        seller_items = [item for item in order.items.all() if item.maker_id == maker.id]
        seller_subtotal = sum((item.line_total for item in seller_items), Decimal("0.00"))
        fulfillment = next((f for f in order.seller_fulfillments.all() if f.maker_id == maker.id), None)
        seller_orders.append({
            "order": order,
            "items": seller_items,
            "item_count": sum(item.quantity for item in seller_items),
            "seller_subtotal": seller_subtotal,
            "fulfillment": fulfillment,
        })

    return render(request, "frontend/seller/order_list.html", {
        "maker": maker,
        "seller_orders": seller_orders,
        "meta_title": f"Orders — {maker.name}",
    })
