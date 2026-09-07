"""Cart and checkout logic.

Two rules run through everything here:

1. Prices come from the database, never from the request. A client may say
   *what* it wants and *how many*, never *how much*.
2. Stock is checked and decremented inside one transaction with the rows
   locked, so two shoppers racing for the last piece cannot both win and stock
   can never go negative.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F

from config.exceptions import EmptyCart, InsufficientStock
from products.models import Product, ProductVariant

from .models import (
    Cart, CartItem, DeliveryMethod, Order, OrderItem, OrderNumberSequence,
    OrderStatus, PaymentStatus, ZERO,
)

logger = logging.getLogger(__name__)
MAX_LINE_QUANTITY = 99


# -- cart resolution ------------------------------------------------------

def get_cart(request, create: bool = True) -> Cart | None:
    """The caller's active cart: theirs if signed in, their session's if not."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        # A shopper may have filled an anonymous bag and only then authenticated
        # (a JWT client, or a session that predates sign-in). Fold it in first,
        # so the bag they built is the bag they check out with.
        session_key = getattr(request, "session", None) and request.session.session_key
        if session_key and Cart.objects.filter(session_key=session_key, user__isnull=True,
                                               is_active=True).exists():
            return merge_session_cart(request, user)

        cart = Cart.objects.filter(user=user, is_active=True).first()
        if cart or not create:
            return cart
        return Cart.objects.create(user=user)

    if not request.session.session_key:
        if not create:
            return None
        request.session.create()
    key = request.session.session_key
    cart = Cart.objects.filter(session_key=key, user__isnull=True, is_active=True).first()
    if cart or not create:
        return cart
    return Cart.objects.create(session_key=key)


@transaction.atomic
def merge_session_cart(request, user) -> Cart:
    """Fold an anonymous cart into the user's on sign-in.

    Quantities are summed and re-clamped to available stock, so merging can
    never create an unfulfillable line.
    """
    session_key = request.session.session_key
    user_cart, _ = Cart.objects.get_or_create(user=user, is_active=True)
    if not session_key:
        return user_cart

    anon = Cart.objects.filter(session_key=session_key, user__isnull=True, is_active=True).first()
    if not anon or anon.pk == user_cart.pk:
        return user_cart

    for item in anon.items.select_related("product", "variant"):
        existing = user_cart.items.filter(product=item.product, variant=item.variant).first()
        wanted = (existing.quantity if existing else 0) + item.quantity
        allowed = min(wanted, _available_for(item.product, item.variant), MAX_LINE_QUANTITY)
        if allowed <= 0:
            continue
        if existing:
            existing.quantity = allowed
            existing.save(update_fields=["quantity", "updated_at"])
        else:
            CartItem.objects.create(cart=user_cart, product=item.product,
                                    variant=item.variant, quantity=allowed)
    anon.delete()
    return user_cart


def _available_for(product: Product, variant: ProductVariant | None) -> int:
    if product.is_made_to_order:
        return MAX_LINE_QUANTITY
    return variant.stock_quantity if variant else product.stock_quantity


# -- cart mutations -------------------------------------------------------

@transaction.atomic
def add_item(cart: Cart, *, product_slug: str, variant_id=None, quantity: int = 1) -> CartItem:
    quantity = _clean_quantity(quantity)

    product = Product.objects.active().filter(slug=product_slug).first()
    if product is None:
        raise Product.DoesNotExist(f"No active product with slug '{product_slug}'.")

    variant = None
    if variant_id:
        variant = ProductVariant.objects.filter(
            product=product, is_active=True
        ).filter(uuid=variant_id).first() if _is_uuid(variant_id) else \
            ProductVariant.objects.filter(product=product, is_active=True, label=variant_id).first()
        if variant is None:
            raise ProductVariant.DoesNotExist("That option is not available for this product.")

    item = cart.items.filter(product=product, variant=variant).first()
    wanted = (item.quantity if item else 0) + quantity
    _assert_stock(product, variant, wanted)

    if item:
        item.quantity = wanted
        item.save(update_fields=["quantity", "updated_at"])
    else:
        item = CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=wanted)
    cart.save(update_fields=["updated_at"])
    return item


@transaction.atomic
def set_quantity(cart: Cart, item_id, quantity: int) -> CartItem | None:
    item = cart.items.select_related("product", "variant").filter(pk=item_id).first()
    if item is None:
        raise CartItem.DoesNotExist("That line is not in your bag.")

    if quantity <= 0:
        item.delete()
        cart.save(update_fields=["updated_at"])
        return None

    quantity = _clean_quantity(quantity)
    _assert_stock(item.product, item.variant, quantity)
    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])
    cart.save(update_fields=["updated_at"])
    return item


def remove_item(cart: Cart, item_id) -> bool:
    deleted, _ = cart.items.filter(pk=item_id).delete()
    if deleted:
        cart.save(update_fields=["updated_at"])
    return bool(deleted)


def clear(cart: Cart) -> None:
    cart.items.all().delete()
    cart.save(update_fields=["updated_at"])


def _clean_quantity(quantity) -> int:
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValueError("Quantity must be a whole number.")
    if quantity < 1:
        raise ValueError("Quantity must be at least 1.")
    return min(quantity, MAX_LINE_QUANTITY)


def _assert_stock(product: Product, variant: ProductVariant | None, wanted: int) -> None:
    available = _available_for(product, variant)
    if wanted > available:
        name = f"{product.name} ({variant.label})" if variant else product.name
        raise InsufficientStock(
            f"Only {available} of {name} {'is' if available == 1 else 'are'} available."
            if available else f"{name} is out of stock."
        )


def _is_uuid(value) -> bool:
    import uuid as uuid_lib
    try:
        uuid_lib.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


# -- totals ---------------------------------------------------------------

def cart_totals(cart: Cart | None, delivery_method: str = DeliveryMethod.STANDARD) -> dict:
    """Server-side money. The only figures the frontend is allowed to show."""
    if cart is None:
        return {"subtotal": ZERO, "shipping": ZERO, "discount": ZERO,
                "total": ZERO, "item_count": 0, "free_shipping_remaining": None}

    from django.conf import settings

    subtotal = cart.subtotal
    shipping = cart.shipping_amount(delivery_method)
    threshold = Decimal(settings.COMMERCE["FREE_SHIPPING_THRESHOLD"])
    remaining = max(threshold - subtotal, ZERO) if subtotal < threshold else ZERO
    return {
        "subtotal": subtotal,
        "shipping": shipping,
        "discount": ZERO,
        "total": subtotal + shipping,
        "item_count": cart.item_count,
        "free_shipping_remaining": remaining,
    }


# -- checkout -------------------------------------------------------------

@transaction.atomic
def create_order(
    *,
    cart: Cart,
    email: str,
    shipping_address: dict,
    user=None,
    billing_address: dict | None = None,
    delivery_method: str = DeliveryMethod.STANDARD,
    phone: str = "",
    gift_note: str = "",
) -> Order:
    """Turn a cart into an immutable order.

    Everything below happens in one transaction: if any line fails its stock
    check, nothing is written -- no half-created order, no partial decrement.
    """
    items = list(cart.items.select_related("product", "variant"))
    if not items:
        raise EmptyCart()

    # Lock the inventory rows for the duration, in a stable order to avoid
    # deadlocking against a concurrent checkout touching the same products.
    product_ids = sorted({item.product_id for item in items})
    variant_ids = sorted({item.variant_id for item in items if item.variant_id})

    locked_products = {
        p.pk: p for p in Product.objects.select_for_update().filter(pk__in=product_ids)
    }
    locked_variants = {
        v.pk: v for v in ProductVariant.objects.select_for_update().filter(pk__in=variant_ids)
    }

    # Re-validate against the locked rows -- the cart may be minutes old.
    for item in items:
        product = locked_products[item.product_id]
        variant = locked_variants.get(item.variant_id)
        if not product.is_active:
            raise InsufficientStock(f"{product.name} is no longer available.")
        available = MAX_LINE_QUANTITY if product.is_made_to_order else (
            variant.stock_quantity if variant else product.stock_quantity)
        if item.quantity > available:
            raise InsufficientStock(
                f"Only {available} of {product.name} remain — please adjust your bag."
            )

    subtotal = sum(
        ((locked_variants[i.variant_id].price_override
          if i.variant_id and locked_variants[i.variant_id].price_override is not None
          else locked_products[i.product_id].price) * i.quantity
         for i in items),
        ZERO,
    )
    shipping = cart.shipping_amount(delivery_method)

    order = Order.objects.create(
        order_number=OrderNumberSequence.next_number(),
        user=user if (user is not None and user.is_authenticated) else None,
        status=OrderStatus.PENDING,
        payment_status=PaymentStatus.UNPAID,
        subtotal=subtotal,
        shipping_amount=shipping,
        discount_amount=ZERO,
        total=subtotal + shipping,
        currency=locked_products[items[0].product_id].currency,
        customer_email=email,
        customer_phone=phone,
        shipping_address_snapshot=shipping_address,
        billing_address_snapshot=billing_address or shipping_address,
        delivery_method=delivery_method,
        gift_note=gift_note,
    )

    for item in items:
        product = locked_products[item.product_id]
        variant = locked_variants.get(item.variant_id)
        unit_price = (variant.price_override
                      if variant and variant.price_override is not None else product.price)

        OrderItem.objects.create(
            order=order,
            product=product,
            variant=variant,
            maker=product.maker,
            sku=variant.sku if variant else "",
            product_slug=product.slug,
            product_name=product.name,
            maker_name=product.maker.name,
            variant_name=variant.label if variant else "",
            image=product.primary_image(),
            unit_price=unit_price,
            quantity=item.quantity,
            line_total=unit_price * item.quantity,
        )

        # Decrement with an F() expression so the write is atomic in SQL, and
        # guard the update so it can never take a row below zero.
        if not product.is_made_to_order:
            if variant:
                updated = ProductVariant.objects.filter(
                    pk=variant.pk, stock_quantity__gte=item.quantity
                ).update(stock_quantity=F("stock_quantity") - item.quantity)
            else:
                updated = Product.objects.filter(
                    pk=product.pk, stock_quantity__gte=item.quantity
                ).update(stock_quantity=F("stock_quantity") - item.quantity)
            if not updated:
                raise InsufficientStock(f"{product.name} sold out while you were checking out.")

        product.refresh_from_db(fields=["stock_quantity"])
        product.refresh_stock_status()

    cart.items.all().delete()
    cart.is_active = False
    cart.save(update_fields=["is_active", "updated_at"])

    logger.info("Order %s created with %d lines", order.order_number, len(items))
    return order
