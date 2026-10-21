"""Returns: a buyer reports a problem with one purchased line, its seller decides.

The policy shown to buyers (frontend.mockdata.content.SHIPPING_PAGE) is the
source of these rules:

* returns are accepted within thirty days of delivery -- no delivery timestamp
  is stored, so the window runs from the seller's `shipped_at` plus a week's
  delivery allowance;
* a damaged piece needs a photograph and does not have to be sent back;
* made-to-order pieces can only be returned for a problem, not a change of mind.

Every write goes through this module so the browser views (and any later API)
share one set of rules. No money moves: a refund is recorded on the request,
because the payment providers do not implement refunds yet.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from products.models import Maker

from .models import (
    OrderItem, OrderStatus, PaymentStatus, ReturnReason, ReturnRequest, ReturnStatus,
)

RETURN_WINDOW = timedelta(days=30 + 7)
PHOTO_REQUIRED_REASONS = {ReturnReason.DAMAGED}
PROBLEM_REASONS = {ReturnReason.DAMAGED, ReturnReason.FAULTY, ReturnReason.WRONG_ITEM,
                   ReturnReason.NOT_AS_DESCRIBED}

OPEN_STATUSES = (ReturnStatus.REQUESTED, ReturnStatus.APPROVED)

# action -> resulting status, and the statuses each action may start from.
DECISIONS = {
    "approve": (ReturnStatus.APPROVED, {ReturnStatus.REQUESTED}),
    "reject": (ReturnStatus.REJECTED, {ReturnStatus.REQUESTED, ReturnStatus.APPROVED}),
    "refund": (ReturnStatus.REFUNDED, {ReturnStatus.REQUESTED, ReturnStatus.APPROVED}),
    "replace": (ReturnStatus.REPLACED, {ReturnStatus.REQUESTED, ReturnStatus.APPROVED}),
}


def returnable_quantity(item: OrderItem) -> int:
    """Units of this line not already covered by a request (rejected ones are free again)."""
    claimed = (item.return_requests.exclude(status=ReturnStatus.REJECTED)
               .aggregate(total=Sum("quantity"))["total"] or 0)
    return max(item.quantity - claimed, 0)


def _shipped_at(order, maker_id):
    """When this seller's part of the order left, or None if it has not.

    Orders placed before per-seller fulfilment have no SellerFulfillment rows;
    for those the order-level status decides, and with no ship date recorded
    the window is counted from when the order was placed.
    """
    fulfillment = order.seller_fulfillments.filter(maker_id=maker_id).first()
    if fulfillment is not None:
        return fulfillment.shipped_at
    if order.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
        return order.placed_at
    return None


def return_eligibility_error(item: OrderItem, *, now=None) -> str | None:
    """Why this line cannot be returned right now, or None if it can."""
    order = item.order
    if order.payment_status != PaymentStatus.PAID or order.status == OrderStatus.CANCELLED:
        return "Only paid orders that have not been cancelled can be returned."
    if item.maker_id is None:
        return "The maker of this piece is no longer selling here. Please contact the studio."
    shipped_at = _shipped_at(order, item.maker_id)
    if shipped_at is None:
        return "This piece has not been sent yet. Contact the studio if you would like to cancel it."
    if (now or timezone.now()) - shipped_at > RETURN_WINDOW:
        return "The thirty-day return window for this piece has closed."
    if returnable_quantity(item) <= 0:
        return "A return has already been requested for every unit of this piece."
    return None


@transaction.atomic
def request_return(item: OrderItem, *, buyer, quantity: int, reason: str,
                   details: str = "", photo: str = "") -> ReturnRequest:
    # Lock the line so two concurrent requests cannot both claim the last unit.
    item = (OrderItem.objects.select_for_update(of=("self",))
            .select_related("order", "product").get(pk=item.pk))
    if buyer is None or item.order.user_id != buyer.pk:
        raise PermissionDenied("You do not have access to this order.")

    error = return_eligibility_error(item)
    if error:
        raise ValidationError(error)
    if reason not in ReturnReason.values:
        raise ValidationError({"reason": "Choose a reason for the return."})
    available = returnable_quantity(item)
    if not 1 <= quantity <= available:
        raise ValidationError({"quantity": f"Choose between 1 and {available}."})
    if (reason not in PROBLEM_REASONS and item.product is not None
            and item.product.is_made_to_order):
        raise ValidationError({"reason": "Made-to-order pieces can only be returned if there "
                                         "is a problem with them."})
    if reason in PHOTO_REQUIRED_REASONS and not photo:
        raise ValidationError({"photo": "Add a photograph of the damage."})

    return_request = ReturnRequest.objects.create(
        order=item.order, order_item=item, maker_id=item.maker_id, buyer=buyer,
        quantity=quantity, reason=reason, details=details.strip(), photo=photo,
    )
    from content.services import send_return_requested
    transaction.on_commit(lambda: send_return_requested(return_request))
    return return_request


def max_refund(return_request: ReturnRequest) -> Decimal:
    """The value of the units on this request, less anything already refunded on the line."""
    item = return_request.order_item
    refunded = (item.return_requests.filter(status=ReturnStatus.REFUNDED)
                .exclude(pk=return_request.pk)
                .aggregate(total=Sum("refund_amount"))["total"] or Decimal("0.00"))
    return max(min(return_request.requested_value, item.line_total - refunded), Decimal("0.00"))


@transaction.atomic
def decide_return(return_request: ReturnRequest, *, acting_maker: Maker, action: str,
                  seller_note: str = "", refund_amount: Decimal | None = None) -> ReturnRequest:
    """Apply a seller's decision. Settled requests (rejected, refunded, replaced) are final."""
    return_request = (ReturnRequest.objects.select_for_update(of=("self",))
                      .select_related("order", "order_item", "maker").get(pk=return_request.pk))
    if return_request.maker_id != acting_maker.pk:
        raise PermissionDenied("You do not have access to this return.")
    if action not in DECISIONS:
        raise ValidationError({"action": "Choose what to do with this return."})

    new_status, allowed_from = DECISIONS[action]
    if return_request.status not in allowed_from:
        raise ValidationError(f"This return is already {return_request.get_status_display().lower()} "
                              f"and cannot be changed.")
    seller_note = seller_note.strip()
    if action == "reject" and not seller_note:
        raise ValidationError({"seller_note": "Tell the buyer why the return was rejected."})

    if action == "refund":
        limit = max_refund(return_request)
        amount = limit if refund_amount is None else refund_amount
        if amount <= 0 or amount > limit:
            raise ValidationError({"refund_amount": f"Enter an amount above 0 and no more than {limit}."})
        return_request.refund_amount = amount

    now = timezone.now()
    return_request.status = new_status
    if seller_note:
        return_request.seller_note = seller_note
    return_request.decided_at = return_request.decided_at or now
    if new_status not in OPEN_STATUSES:
        return_request.resolved_at = now
    return_request.save(update_fields=["status", "seller_note", "refund_amount", "decided_at",
                                       "resolved_at", "updated_at"])

    from content.services import send_return_update
    transaction.on_commit(lambda: send_return_update(return_request))
    return return_request


def open_return_count(maker: Maker) -> int:
    return ReturnRequest.objects.filter(maker=maker, status__in=OPEN_STATUSES).count()
