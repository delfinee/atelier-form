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


def send_welcome(user) -> bool:
    return get_email_sender().send(
        to=user.email, subject="Welcome to Atelier Form",
        body="Your account is ready.",
    )
