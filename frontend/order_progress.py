"""Buyer-facing order progress, derived read-only from seller fulfilments.

Order.status is the commercial lifecycle and nothing here writes it. Sellers
ship through the shared fulfilment service, which deliberately leaves
Order.status alone, so a buyer would otherwise keep seeing "Confirmed" after
every parcel has left. This module works out a display-only *effective*
status and renders it through the existing status/timeline/localisation
helpers, so every buyer page agrees and Chinese output is unchanged.

Only a paid CONFIRMED/PROCESSING order whose every seller has shipped is shown
as on its way. Every other stored status -- SHIPPED set by the concierge flow,
DELIVERED, CANCELLED, or any status added later -- is shown exactly as stored,
and a stored status is never shown as an earlier one.
"""
from copy import copy

from orders.models import FulfillmentStatus, OrderStatus, PaymentStatus

from .catalogue_i18n import (
    localize_maker, localize_order_status, localize_order_timeline, localize_short_date,
)

PROMOTABLE_STATUSES = frozenset({OrderStatus.CONFIRMED, OrderStatus.PROCESSING})
# Payment never succeeded, so any fulfilment rows are stale; show no shipments.
NEVER_PAID = frozenset({PaymentStatus.UNPAID, PaymentStatus.PENDING, PaymentStatus.FAILED})
DISPATCHED_STEP = "Dispatched"  # Order.timeline's label for the shipping step
# Order.timeline dates every completed step with placed_at. For these later
# milestones that is not evidence of when they happened, so the buyer view
# shows a recorded date (Dispatched: the sellers' shipped_at) or none at all.
UNRECORDED_DATE_STEPS = frozenset({"Made & packed", DISPATCHED_STEP, "Delivered"})


def _every_seller_shipped(fulfillments, items) -> bool:
    """True when each maker in the order has exactly one fulfilment and all
    of them are FULFILLED. A line without a maker, or a maker without a
    fulfilment row (legacy data), means the whole order cannot be claimed."""
    makers = {item.maker_id for item in items}
    return (bool(items) and None not in makers
            and len(fulfillments) == len(makers)
            and {f.maker_id for f in fulfillments} == makers
            and all(f.status == FulfillmentStatus.FULFILLED for f in fulfillments))


def _shown_as(order, status):
    """`order` presented with another lifecycle status. A shallow copy used only
    to drive the existing display helpers; it is never saved."""
    if status == order.status:
        return order
    shown = copy(order)
    shown.status = status
    return shown


def buyer_order_progress(order) -> dict:
    """Effective status code, localised label and timeline, and per-seller
    shipment history for one of the buyer's orders.

    Reads `order.items` and `order.seller_fulfillments` (prefetch them, with
    `seller_fulfillments__maker`, to avoid per-order queries).
    """
    if order.pk is None:  # not saved yet, so no seller can have shipped any of it
        fulfillments, items = [], []
    else:
        fulfillments = list(order.seller_fulfillments.all())
        items = list(order.items.all())
    all_shipped = _every_seller_shipped(fulfillments, items)

    status = order.status
    if (all_shipped and order.status in PROMOTABLE_STATUSES
            and order.payment_status == PaymentStatus.PAID):
        status = OrderStatus.SHIPPED
    shown = _shown_as(order, status)

    ship_dates = [f.shipped_at for f in fulfillments]
    # The real dispatch date is when the last seller's parcel left; without a
    # shipped_at for every seller it is unknown. No packing or delivery
    # timestamp is recorded, so those completed steps carry no date.
    dispatched_on = (localize_short_date(max(ship_dates))
                     if all_shipped and all(ship_dates) else "")
    timeline = [
        {**step, "date": dispatched_on if raw["label"] == DISPATCHED_STEP else ""}
        if step["done"] and raw["label"] in UNRECORDED_DATE_STEPS else step
        for raw, step in zip(shown.timeline, localize_order_timeline(shown))
    ]

    shipments = []
    if order.payment_status not in NEVER_PAID:
        for f in fulfillments:
            dispatched = f.status == FulfillmentStatus.FULFILLED
            if not dispatched and not (f.status == FulfillmentStatus.PARTIAL and f.tracking_number):
                continue
            shipments.append({
                "maker": localize_maker(f.maker).name,
                "dispatched": dispatched,
                "date": localize_short_date(f.shipped_at) if dispatched and f.shipped_at else "",
                "carrier": f.carrier,
                "tracking_number": f.tracking_number,
            })

    return {
        "status": status,
        "label": localize_order_status(shown.status_label),
        "timeline": timeline,
        "shipments": shipments,
    }
