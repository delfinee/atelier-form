"""All commerce decisions live here; model output is only a suggestion."""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied

from orders.models import Cart, CartItem, Order, OrderStatus, PaymentStatus, SellerFulfillment, FulfillmentStatus
from orders.services import cart_totals, create_order, update_seller_fulfillment
from payments.models import PaymentState
from payments.services import MockPaymentProvider
from products.models import Product, ProductVariant
from .text import text
from .models import Conversation, OrderDraft, Event


def require_demo():
    if not ((settings.DEBUG or settings.PUBLIC_CONCIERGE_DEMO) and settings.CONCIERGE_DEMO and
            settings.PAYMENT_BACKEND == "payments.services.MockPaymentProvider"):
        raise PermissionDenied(text("微信客服模拟台仅在本地演示模式下开放。", "The assistant is available only in demo mode."))


def scoped_conversation(actor, uuid, *, lock=False):
    qs = Conversation.objects.select_for_update() if lock else Conversation.objects
    return get_object_or_404(qs, uuid=uuid, maker__owner=actor, maker__is_active=True)


def catalogue(maker):
    return [{"product": p.slug, "name": p.name, "price": str(p.price),
             "stock": p.stock_quantity, "made_to_order": p.is_made_to_order,
             "variants": [{"id": str(v.uuid), "label": v.label, "price": str(v.unit_price),
                           "stock": v.stock_quantity} for v in p.product_variants.all() if v.is_active]}
            for p in Product.objects.filter(maker=maker, is_active=True)
            .prefetch_related("product_variants").order_by("name")]


def build_cart(maker, lines, key):
    """Lock product then variant rows in deterministic order; reject stale SKUs."""
    products = {p.slug: p for p in Product.objects.select_for_update()
                .filter(slug__in=[l["product"] for l in lines]).order_by("pk")}
    variants = {str(v.uuid): v for v in ProductVariant.objects.select_for_update()
                .filter(product__in=list(products.values())).order_by("pk")}
    cart = Cart.objects.create(session_key=key)
    snapshots, seen = [], set()
    for line in lines:
        p = products.get(line["product"])
        if not p or not p.is_active or p.maker_id != maker.pk or p.currency != settings.CURRENCY:
            raise ValidationError(text("商品已下架、货币不符或不属于当前商家。", "This product is unavailable, uses a different currency, or belongs to another seller."))
        variant_id = str(line.get("variant") or "")
        v = variants.get(variant_id)
        if variant_id and (not v or not v.is_active or v.product_id != p.pk):
            raise ValidationError(text("商品规格已失效，请重新选择。", "This option is no longer available. Please choose again."))
        if not variant_id and any(x.product_id == p.pk for x in variants.values()):
            raise ValidationError(text("请选择商品规格。", "Please choose a product option."))
        identity = (p.pk, variant_id)
        if identity in seen:
            raise ValidationError(text("同一商品规格请合并数量。", "Combine quantities for the same product option."))
        seen.add(identity)
        qty = line["quantity"]
        if isinstance(qty, bool) or not isinstance(qty, int) or not 1 <= qty <= 99:
            raise ValidationError(text("数量必须为 1–99 的整数。", "Quantity must be a whole number from 1 to 99."))
        if not p.is_made_to_order and qty > (v.stock_quantity if v else p.stock_quantity):
            raise ValidationError(text(f"{p.name} 库存不足，请调整数量。", f"Not enough stock for {p.name}. Please reduce the quantity."))
        price = v.price_override if v and v.price_override is not None else p.price
        CartItem.objects.create(cart=cart, product=p, variant=v, quantity=qty)
        snapshots.append({"product": p.slug, "variant": variant_id or None,
                          "quantity": qty, "name": p.name, "option": v.label if v else "",
                          "unit_price": str(price), "line_total": str(price * qty)})
    return cart, snapshots


@transaction.atomic
def make_draft(actor, conversation_id, data):
    require_demo()
    conversation = scoped_conversation(actor, conversation_id, lock=True)
    existing = conversation.drafts.filter(request_id=data["request_id"]).first()
    if existing:
        return existing
    cart, lines = build_cart(conversation.maker, data["lines"], f"quote:{data['request_id']}")
    totals = cart_totals(cart, data["delivery_method"])
    cart.delete()  # A quote reserves nothing and never changes stock.
    draft = OrderDraft.objects.create(
        conversation=conversation, request_id=data["request_id"], created_by=actor, lines=lines,
        customer={k: data[k] for k in ("email", "phone", "shipping_address")},
        delivery_method=data["delivery_method"], total=totals["total"], shipping=totals["shipping"],
        expires_at=timezone.now() + timedelta(minutes=30))
    Event.objects.create(draft=draft, actor=actor, action="draft_created")
    return draft


@transaction.atomic
def act(actor, draft_id, data):
    require_demo()
    # Keep nullable order/payment relations out of the locking query.
    draft = get_object_or_404(OrderDraft.objects.select_for_update(), uuid=draft_id,
                             conversation__maker__owner=actor, conversation__maker__is_active=True)
    action = data["action"]
    if action == "confirm":
        if not data.get("confirmed"):
            raise ValidationError(text("请明确确认草稿。", "Please explicitly confirm the draft."))
        if draft.order_id:
            return draft
        if timezone.now() >= draft.expires_at:
            raise ValidationError(text("草稿已过期，请重新报价。", "This draft has expired. Please create a new draft."))
        cart, current = build_cart(draft.conversation.maker, draft.lines, f"order:{draft.uuid}")
        totals = cart_totals(cart, draft.delivery_method)
        if current != draft.lines or totals["total"] != draft.total or totals["shipping"] != draft.shipping:
            raise ValidationError(text("商品或价格发生变化，请重新生成并确认草稿。", "Products or prices have changed. Please create and confirm a new draft."))
        draft.order = create_order(cart=cart, user=None, delivery_method=draft.delivery_method, **draft.customer)
        draft.payment = MockPaymentProvider().create_session(
            draft.order, return_url="/seller/assistant/" if settings.PUBLIC_CONCIERGE_DEMO else ""
        ).payment
        draft.save(update_fields=["order", "payment", "updated_at"])
    else:
        if not draft.order_id:
            raise ValidationError(text("请先确认订单。", "Please confirm the order first."))
        order = Order.objects.select_for_update().get(pk=draft.order_id)
        if order.status == OrderStatus.CANCELLED or order.payment_status in (PaymentStatus.REFUNDED, PaymentStatus.FAILED):
            raise ValidationError(text("该订单已取消、退款或付款失败，不能继续操作。", "This order was cancelled, refunded, or its payment failed. No further actions are available."))
        if action == "pay":
            if order.payment_status == PaymentStatus.PAID:
                return draft
            payment = MockPaymentProvider().confirm(draft.payment)
            if payment.state != PaymentState.SUCCEEDED:
                raise ValidationError(text("付款预留已失效，请重新下单。", "The payment reservation has expired. Please create a new order."))
        else:
            if order.payment_status != PaymentStatus.PAID:
                raise ValidationError(text("收到付款后才能打包发货。", "Payment must be received before packing or shipping."))
            fulfillment = SellerFulfillment.objects.select_for_update().get(order=order, maker=draft.conversation.maker)
            if action == "pack":
                if draft.packing_started_at:
                    return draft
                draft.packing_started_at = timezone.now()
                order.status = OrderStatus.PROCESSING
                order.save(update_fields=["status", "updated_at"])
                draft.save(update_fields=["packing_started_at", "updated_at"])
            elif action == "packed":
                if not draft.packing_started_at:
                    raise ValidationError(text("请先开始拣货打包。", "Please start picking and packing first."))
                if draft.packed_at:
                    return draft
                draft.packed_at = timezone.now()
                draft.save(update_fields=["packed_at", "updated_at"])
            elif action == "ship":
                if not draft.packed_at:
                    raise ValidationError(text("完成打包核对后才能发货。", "Complete packing checks before shipping."))
                if fulfillment.shipped_at:
                    if (fulfillment.carrier, fulfillment.tracking_number) != (data["carrier"], data["tracking_number"]):
                        raise ValidationError(text("订单已发货，不能覆盖原运单。", "This order has shipped. The original tracking details cannot be replaced."))
                    return draft
                update_seller_fulfillment(fulfillment, acting_maker=draft.conversation.maker,
                                         status=FulfillmentStatus.FULFILLED,
                                         carrier=data["carrier"], tracking_number=data["tracking_number"])
                order.status = OrderStatus.SHIPPED
                order.carrier, order.tracking_number = data["carrier"], data["tracking_number"]
                order.save(update_fields=["status", "carrier", "tracking_number", "updated_at"])
    Event.objects.create(draft=draft, actor=actor, action=action)
    return draft


def draft_data(draft):
    order = draft.order
    return {"id": str(draft.uuid), "lines": draft.lines, "customer": draft.customer,
            "total": str(draft.total), "shipping": str(draft.shipping), "currency": settings.CURRENCY,
            "expires_at": draft.expires_at.isoformat(), "expired": timezone.now() >= draft.expires_at,
            "packing_started": bool(draft.packing_started_at), "packed": bool(draft.packed_at),
            "order": {"number": order.order_number, "status": order.status,
                      "payment_status": order.payment_status, "carrier": order.carrier,
                      "tracking_number": order.tracking_number} if order else None,
            "events": [{"action": e.action, "at": e.created_at.isoformat()} for e in draft.events.all()]}
