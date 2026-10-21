"""Read-only buyer shipping progress derived from seller fulfilments.

Never changes commercial Order.status or the fulfilment write path. A partial
shipment is not an order-wide shipment; cancellation/delivery take precedence.
"""
from django.utils import timezone
from django.utils.translation import gettext as _

from orders.models import FulfillmentStatus, OrderStatus, PaymentStatus


def buyer_shipping_progress(order):
    timeline = order.timeline
    label = order.status_label
    shipments = []
    if order.status in (OrderStatus.CANCELLED, OrderStatus.DELIVERED):
        return {"timeline": timeline, "label": label, "shipments": shipments}

    fulfillments = list(order.seller_fulfillments.all())
    # A legacy order can lack fulfilment rows. Never imply the whole order
    # shipped unless every non-orphaned item is represented by its maker.
    item_maker_ids = [item.maker_id for item in order.items.all()]
    expected_makers = set(item_maker_ids)
    complete_coverage = (
        bool(item_maker_ids) and None not in expected_makers
        and len(fulfillments) == len(expected_makers)
        and {f.maker_id for f in fulfillments} == expected_makers
    )
    shipments = [
        f for f in fulfillments
        if f.status == FulfillmentStatus.FULFILLED
    ]
    # Preserve the order status for not-yet-paid and legacy records.
    if order.payment_status != PaymentStatus.PAID or not complete_coverage:
        return {"timeline": timeline, "label": label, "shipments": shipments}

    if fulfillments and all(f.status == FulfillmentStatus.FULFILLED for f in fulfillments):
        if order.status in (OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.SHIPPED):
            label = _("On its way")
            ship_dates = [f.shipped_at for f in fulfillments if f.shipped_at]
            shipped_date = timezone.localtime(max(ship_dates)).strftime("%d %b").lstrip("0") if ship_dates else _("Shipped")
            # No packing-completed timestamp exists in the seller fulfilment model.
            timeline = [
                {**step, "done": True, "date": _("Completed") if i == 2 else shipped_date}
                if i in (2, 3) else step
                for i, step in enumerate(timeline)
            ]
    elif shipments and order.status in (OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.SHIPPED):
        label = _("Partially dispatched")

    return {"timeline": timeline, "label": label, "shipments": shipments}
