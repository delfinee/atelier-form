"""Channel-neutral operations. Only confirm_change writes commercial records."""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.exceptions import PermissionDenied, ValidationError
from products.models import Maker, Product, ProductVariant, Category
from products.serializers import SellerProductSerializer
from orders.models import Order, OrderItem, SellerFulfillment
from orders.serializers import SellerOrderSerializer
from orders.services import update_seller_fulfillment, is_dispatch_eligible
from .models import Conversation, Change
from .serializers import InventoryInput, PriceInput, ListingInput, FulfillmentInput


def require_seller(user, lock=False):
    if not get_user_model().objects.filter(pk=user.pk, is_active=True, is_seller=True).exists():
        raise PermissionDenied("An active, verified seller account is required for this operation.")
    qs = Maker.objects.select_for_update() if lock else Maker.objects
    maker = qs.filter(owner=user, is_active=True).first()
    if maker is None:
        raise PermissionDenied("Your website account must be linked to an active shop by the existing onboarding process.")
    maker._shared_catalogue = getattr(user, "_shared_catalogue", False)
    return maker


def has_shop(user):
    return bool(getattr(user, "is_seller", False) and Maker.objects.filter(owner_id=user.pk, is_active=True).exists())


def conversation_for(user, uuid, lock=False):
    qs = Conversation.objects.select_for_update() if lock else Conversation.objects
    return get_object_or_404(qs, uuid=uuid, user=user)


def products(user, low_stock=False):
    maker = require_seller(user)
    result = []
    catalogue = Product.objects.all() if maker._shared_catalogue else Product.objects.filter(maker=maker)
    for p in catalogue.prefetch_related("product_variants").order_by("name")[:200]:
        variants = [{"id": str(v.uuid), "label": v.label, "quantity": v.stock_quantity,
                     "price": str(v.unit_price), "active": v.is_active} for v in p.product_variants.all()]
        # Keep zero-stock options visible, including a low option on a high-total product.
        low = not p.is_made_to_order and (
            any(v["active"] and v["quantity"] <= settings.COMMERCE["LOW_STOCK_THRESHOLD"] for v in variants)
            if variants else p.stock_quantity <= settings.COMMERCE["LOW_STOCK_THRESHOLD"])
        if not low_stock or low:
            result.append({"slug": p.slug, "name": p.name, "price": str(p.price), "currency": p.currency,
                "quantity": None if p.is_made_to_order else p.available_quantity, "variants": variants, "active": p.is_active,
                "made_to_order": p.is_made_to_order, "low_stock": low,
                "url": "/seller/products/" + p.slug + "/edit/"})
    return result


def orders(user):
    maker = require_seller(user)
    qs = Order.objects.filter(items__maker=maker).distinct().order_by("-placed_at").prefetch_related(
        "items", "items__maker", "seller_fulfillments")[:50]
    result = list(SellerOrderSerializer(qs, many=True, context={"request": SimpleNamespace(user=user)}).data)
    for order, row in zip(qs, result):
        row["seller_subtotal"] = str(row["seller_subtotal"])
        fulfillment = row.get("fulfillment")
        row["can_ship"] = bool(is_dispatch_eligible(order) and fulfillment and not fulfillment.get("shipped_at"))
    return result


def _inventory_target(maker, target, values, lock=False):
    qs = Product.objects.select_for_update() if lock else Product.objects
    if not getattr(maker, "_shared_catalogue", False):
        qs = qs.filter(maker=maker)
    product = get_object_or_404(qs, slug=target)
    variant_id = values.get("variant")
    variant = None
    variants = ProductVariant.objects.select_for_update() if lock else ProductVariant.objects
    if variant_id:
        variant = get_object_or_404(variants, product=product, uuid=variant_id, is_active=True)
    elif product.product_variants.exists() and "quantity" in values:
        raise ValidationError("Select a product option; parent stock is not authoritative for products with options.")
    if "quantity" in values and product.is_made_to_order:
        raise ValidationError("Made-to-order availability is not controlled by stock quantity. Use the product editor.")
    before = {"product": str(product.uuid), "name": product.name, "price": str(product.price),
              "quantity": product.stock_quantity, "active": product.is_active, "made_to_order": product.is_made_to_order}
    if variant:
        before["variant"] = {"id": str(variant.uuid), "label": variant.label, "quantity": variant.stock_quantity,
                             "price": str(variant.unit_price), "active": variant.is_active}
    return product, variant, before


def _fulfillment_target(maker, target, lock=False):
    try:
        order_id = UUID(target)
    except (ValueError, TypeError):
        raise ValidationError("Select an order from your orders list.") from None
    qs = Order.objects.select_for_update() if lock else Order.objects
    order = get_object_or_404(qs.filter(pk__in=OrderItem.objects.filter(maker=maker).values("order_id")), uuid=order_id)
    fs = SellerFulfillment.objects.select_for_update() if lock else SellerFulfillment.objects
    fulfillment = get_object_or_404(fs, order=order, maker=maker)
    before = {"order": str(order.uuid), "number": order.order_number, "order_status": order.status,
        "payment_status": order.payment_status, "status": fulfillment.status, "carrier": fulfillment.carrier,
        "tracking_number": fulfillment.tracking_number, "shipped_at": str(fulfillment.shipped_at or "")}
    return fulfillment, before


def _validate(action, values):
    schema = {"stock": InventoryInput, "price": PriceInput, "listing": ListingInput, "fulfillment": FulfillmentInput}[action]
    extra = set(values) - set(schema().fields)
    if extra:
        raise ValidationError("Unsupported fields: " + ", ".join(sorted(extra)))
    data = schema(data=values)
    data.is_valid(raise_exception=True)
    return {k: str(v) if isinstance(v, (Decimal, UUID)) else v for k, v in data.validated_data.items()}


def _listing_serializer(values):
    category = get_object_or_404(Category, slug=values["category"], is_active=True)
    # Never accept maker, admin flags or a client-selected publication state.
    payload = {"name": values["name"], "category": category.pk, "description": values["description"],
        "price": values["price"], "stock_quantity": values["quantity"], "currency": settings.CURRENCY,
        "slug": (slugify(values["name"])[:150] or "product") + "-" + uuid4().hex[:10], "is_active": False}
    serializer = SellerProductSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    return serializer


@transaction.atomic
def prepare_change(user, conversation_id, request_id, action, target, values):
    conversation = conversation_for(user, conversation_id, lock=True)
    old = conversation.changes.filter(request_id=request_id).first()
    if old:
        return old
    maker = require_seller(user)
    values = _validate(action, values)
    if action in ("stock", "price"):
        _, _, before = _inventory_target(maker, target, values)
    elif action == "fulfillment":
        fulfillment, before = _fulfillment_target(maker, target)
        if not is_dispatch_eligible(fulfillment.order) or fulfillment.shipped_at:
            raise ValidationError("Only a paid, dispatch-eligible, unshipped order can be prepared for shipment here.")
    else:
        _listing_serializer(values)
        before = {"shop": str(maker.uuid), "publication": "unpublished"}
    # Editing a proposed operation invalidates its older pending preview.
    conversation.changes.filter(action=action, target=target, status="pending").update(status="superseded")
    return Change.objects.create(conversation=conversation, request_id=request_id, action=action, target=target,
        values=values, before=before, expires_at=timezone.now()+timedelta(minutes=15))


def change_data(change):
    values, before = change.values, change.before
    if change.action in ("stock", "price"):
        variant = before.get("variant")
        item = before["name"] + (" · " + variant["label"] if variant else "")
        field = "quantity" if change.action == "stock" else "price"
        previous = variant[field] if variant else before[field]
        summary = f"Product: {item}\n{'Available quantity' if field == 'quantity' else 'Price'}: {previous} → {values[field]}"
    elif change.action == "listing":
        summary = (f"Name: {values['name']}\nCategory: {values['category']}\nPrice: {settings.CURRENCY} {values['price']}\n"
                   f"Available quantity: {values['quantity']}\nDescription: {values['description']}\nPublication: unpublished draft")
    else:
        summary = (f"Order: {before['number']}\nFulfillment: {before['status']} → fulfilled\n"
                   f"Carrier: {values['carrier']}\nTracking number: {values['tracking_number']}")
    return {"id": str(change.uuid), "action": change.action, "target": change.target, "before": change.before,
        "values": change.values, "status": change.status, "expires_at": change.expires_at.isoformat(),
        "expired": change.expires_at <= timezone.now(), "result": change.result,
        "confirmed_channel": change.confirmed_channel, "summary": summary}


@transaction.atomic
def confirm_change(user, uuid, channel):
    change = get_object_or_404(Change.objects.select_for_update(), uuid=uuid, conversation__user=user)
    maker = require_seller(user, lock=True)
    if change.status == "applied":
        return change
    if change.status != "pending" or change.expires_at <= timezone.now():
        raise ValidationError("This preview is expired or superseded. Prepare a new one.")
    values = _validate(change.action, change.values)
    if change.action in ("stock", "price"):
        product, variant, current = _inventory_target(maker, change.target, values, lock=True)
        if current != change.before:
            raise ValidationError("Product or stock changed since this preview. Review a new preview.")
        obj = variant or product
        field = "stock_quantity" if change.action == "stock" else ("price_override" if variant else "price")
        setattr(obj, field, values["quantity"] if change.action == "stock" else Decimal(values["price"]))
        obj.save(update_fields=[field, "updated_at"])
        product.refresh_stock_status()
        change.result = {"message": "Product updated.", "product": product.slug,
                         "url": "/seller/products/" + product.slug + "/edit/"}
    elif change.action == "listing":
        if change.before["shop"] != str(maker.uuid):
            raise ValidationError("Shop ownership changed. Prepare a new draft.")
        serializer = _listing_serializer(values)
        product = serializer.save(maker=maker)
        product.refresh_stock_status()
        change.result = {"message": "Unpublished product draft saved. Add images and options in the product editor before publishing.",
                         "product": product.slug, "url": "/seller/products/" + product.slug + "/edit/"}
    else:
        fulfillment, current = _fulfillment_target(maker, change.target, lock=True)
        if current != change.before:
            raise ValidationError("Order or fulfillment changed. Review a new preview.")
        update_seller_fulfillment(fulfillment, acting_maker=maker, **values)
        change.result = {"message": "Your shop's fulfillment was updated.", "order": change.target,
                         "tracking_number": fulfillment.tracking_number}
    change.status = "applied"
    change.confirmed_channel = channel
    change.save(update_fields=["status", "result", "confirmed_channel", "updated_at"])
    return change
