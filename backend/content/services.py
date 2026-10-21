"""Outbound notification abstraction.

Nothing in the app blocks on email delivery: registration and checkout succeed
whether or not a message can be sent. Swap `EMAIL_BACKEND_CLASS` for a real
sender later (Resend, SendGrid, Amazon SES) without touching call sites.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class EmailSender(ABC):
    @abstractmethod
    def send(self, *, to: str, subject: str, body: str) -> bool:
        """Deliver one message. Must never raise into the caller."""


class ConsoleEmailSender(EmailSender):
    """Development sender: logs that a message *would* be sent.

    Logs the recipient and subject only. Never log tokens, passwords, reset
    links or payment identifiers.
    """

    def send(self, *, to: str, subject: str, body: str) -> bool:
        logger.info("Email would be sent to %s — %s", to, subject)
        return True


class NullEmailSender(EmailSender):
    """Used in tests to keep output quiet."""

    def send(self, *, to: str, subject: str, body: str) -> bool:
        return True


def get_email_sender() -> EmailSender:
    return import_string(settings.EMAIL_SENDER_CLASS)()


def send_order_confirmation(order) -> bool:
    return get_email_sender().send(
        to=order.customer_email,
        subject=f"Your order {order.order_number}",
        body=f"Thank you. Order {order.order_number} totalling {order.total} {order.currency} is confirmed.",
    )

def send_order_shipped(fulfillment, *, whole_order: bool) -> bool:
    """Tell the buyer one seller's part of their order has shipped.

    `whole_order` is decided by the caller: True only when every line in the
    order belongs to this fulfilment's seller. Otherwise the message says
    which seller's items are on their way and that the rest ship separately,
    rather than claiming the whole order has left.
    """
    order = fulfillment.order
    number = order.order_number
    if whole_order:
        subject = f"Your order {number} has shipped"
        lines = [f"Good news — order {number} is on its way."]
    else:
        subject = f"Part of your order {number} has shipped"
        lines = [f"Good news — the items from {fulfillment.maker.name} in order {number} "
                 f"are on their way. Other items in this order ship separately."]

    tracking = [part for part in (
        f"Carrier: {fulfillment.carrier}" if fulfillment.carrier else "",
        f"Tracking number: {fulfillment.tracking_number}" if fulfillment.tracking_number else "",
    ) if part]
    if tracking:
        lines.append(" · ".join(tracking))

    return get_email_sender().send(to=order.customer_email, subject=subject,
                                   body="\n\n".join(lines))


def send_order_delivered(order) -> bool:
    return get_email_sender().send(
        to=order.customer_email,
        subject=f"Your order {order.order_number} has been delivered",
        body=(f"Order {order.order_number} has arrived. We hope you love it — "
              f"thank you for supporting a small maker."),
    )


def send_return_requested(return_request) -> bool:
    """Tell the seller a buyer has asked to return one of their pieces."""
    owner = return_request.maker.owner
    if owner is None or not owner.email:
        return False
    item = return_request.order_item
    return get_email_sender().send(
        to=owner.email,
        subject=f"Return requested on order {return_request.order.order_number}",
        body=(f"A buyer has asked to return {return_request.quantity} × {item.product_name} "
              f"({return_request.get_reason_display()}). Review it in your seller returns page."),
    )


def send_return_update(return_request) -> bool:
    """Tell the buyer what the seller decided."""
    order = return_request.order
    lines = [f"Your return for {return_request.order_item.product_name} in order "
             f"{order.order_number} is now: {return_request.get_status_display()}."]
    if return_request.refund_amount is not None and return_request.status == "refunded":
        lines.append(f"Refund: {return_request.refund_amount} {order.currency}.")
    if return_request.seller_note:
        lines.append(f"Note from the maker: {return_request.seller_note}")
    return get_email_sender().send(to=order.customer_email,
                                   subject=f"Update on your return for order {order.order_number}",
                                   body="\n\n".join(lines))


def send_welcome(user) -> bool:
    return get_email_sender().send(
        to=user.email, subject="Welcome to Atelier Form",
        body="Your account is ready.",
    )
