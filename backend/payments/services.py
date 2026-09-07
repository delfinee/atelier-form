"""Payment provider abstraction.

The real integration point. A provider is handed an Order and returns a session
the customer is redirected to; the provider later calls back and the order is
marked paid *only* by `handle_webhook`, never by anything the browser says.

    Backend creates payment session
            v
    Payment provider
            v
    Customer completes payment
            v
    Provider webhook  -->  verify signature  -->  order marked paid

To add Stripe's native WeChat Pay (the charter's choice), implement
`StripeWeChatProvider` below and point PAYMENT_BACKEND at it. No other module
needs to change.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from django.utils.module_loading import import_string

from .models import Payment, PaymentProviderChoices, PaymentState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaymentSession:
    """What a provider hands back after a session is created."""

    payment: Payment
    session_id: str
    checkout_url: str
    requires_action: bool


class PaymentProvider(ABC):
    """Contract every provider must satisfy.

    Implementations must never accept or persist raw card data. Card details go
    from the customer's browser straight to the provider.
    """

    name: str = "abstract"

    @abstractmethod
    def create_session(self, order, *, return_url: str = "") -> PaymentSession:
        """Open a payment session for an order."""

    @abstractmethod
    def handle_webhook(self, raw_body: bytes, headers: dict) -> Payment | None:
        """Verify a provider callback and move the payment to its final state."""

    def refund(self, payment: Payment, amount: Decimal | None = None) -> Payment:
        raise NotImplementedError(f"{self.name} does not support refunds yet.")


class MockPaymentProvider(PaymentProvider):
    """Development provider. Requires no API key and moves no money.

    Creates a real Payment row in the `created` state so the whole checkout
    path -- including the webhook that marks an order paid -- is exercised
    end to end. `confirm` stands in for the provider callback.
    """

    name = PaymentProviderChoices.MOCK

    def create_session(self, order, *, return_url: str = "") -> PaymentSession:
        session_id = f"mock_sess_{uuid.uuid4().hex[:24]}"
        payment = Payment.objects.create(
            order=order,
            provider=self.name,
            state=PaymentState.CREATED,
            amount=order.total,
            currency=order.currency,
            provider_session_id=session_id,
            checkout_url=return_url,
        )
        if not payment.checkout_url:
            payment.checkout_url = reverse("mock_payment", kwargs={"uuid": payment.uuid})
            payment.save(update_fields=["checkout_url", "updated_at"])
        logger.info("Mock payment session created for order %s", order.order_number)
        return PaymentSession(payment=payment, session_id=session_id,
                              checkout_url=payment.checkout_url, requires_action=False)

    @transaction.atomic
    def confirm(self, payment: Payment, *, succeed: bool = True,
                failure_reason: str = "Mock provider was asked to decline.") -> Payment:
        """Stand-in for the provider callback, used by tests and the dev flow."""
        from orders.models import OrderStatus, PaymentStatus

        payment = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)
        order = payment.order
        if succeed:
            # Provider retries are normal. Never send a second confirmation or
            # mutate an already-final payment.
            if payment.state == PaymentState.SUCCEEDED:
                return payment
            # A failed/expired reservation cannot later become paid: its stock
            # may already have been sold to somebody else.
            if payment.inventory_released_at:
                return payment
            payment.state = PaymentState.SUCCEEDED
            payment.provider_payment_id = f"mock_pay_{uuid.uuid4().hex[:24]}"
            order.payment_status = PaymentStatus.PAID
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CONFIRMED
        else:
            if payment.state in {PaymentState.SUCCEEDED, PaymentState.REFUNDED}:
                return payment
            payment.state = PaymentState.FAILED
            payment.failure_reason = failure_reason[:200]
            order.payment_status = PaymentStatus.FAILED
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
            release_reserved_inventory(payment)
        payment.save(update_fields=["state", "provider_payment_id", "failure_reason",
                                    "inventory_released_at", "updated_at"])
        order.save(update_fields=["payment_status", "status", "updated_at"])
        if succeed:
            from content.services import send_order_confirmation
            transaction.on_commit(lambda: send_order_confirmation(order))
        return payment

    def handle_webhook(self, raw_body: bytes, headers: dict) -> Payment | None:
        """A real provider verifies a signature here before trusting anything."""
        import json

        try:
            event = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            logger.warning("Mock webhook received malformed JSON")
            return None

        session_id = event.get("session_id")
        payment = Payment.objects.filter(provider_session_id=session_id).first()
        if not payment:
            logger.warning("Mock webhook for unknown session")
            return None
        return self.confirm(payment, succeed=event.get("status") == "succeeded")


class StripeWeChatProvider(PaymentProvider):
    """Placeholder for the charter's Stripe native WeChat Pay integration.

    Deliberately unimplemented: wiring it needs STRIPE_SECRET_KEY and
    STRIPE_WEBHOOK_SECRET, and the project must run without third-party keys.
    """

    name = PaymentProviderChoices.STRIPE_WECHAT

    def create_session(self, order, *, return_url: str = "") -> PaymentSession:
        raise NotImplementedError(
            "Stripe WeChat Pay is not configured. Set STRIPE_SECRET_KEY and "
            "STRIPE_WEBHOOK_SECRET, then implement create_session with "
            "stripe.checkout.Session.create(payment_method_types=['wechat_pay'], ...)."
        )

    def handle_webhook(self, raw_body: bytes, headers: dict) -> Payment | None:
        raise NotImplementedError(
            "Verify with stripe.Webhook.construct_event(raw_body, "
            "headers['Stripe-Signature'], STRIPE_WEBHOOK_SECRET) before trusting the event."
        )


def get_payment_provider() -> PaymentProvider:
    """Resolve the configured provider. Defaults to the mock one."""
    return import_string(settings.PAYMENT_BACKEND)()


def release_reserved_inventory(payment: Payment) -> bool:
    """Return an unpaid order's stock once; caller must hold a payment lock."""
    if payment.inventory_released_at:
        return False

    from products.models import Product, ProductVariant

    product_ids = set()
    for item in payment.order.items.select_related("product", "variant"):
        product = item.product
        if product is None or product.is_made_to_order:
            continue
        if item.variant_id:
            ProductVariant.objects.filter(pk=item.variant_id).update(
                stock_quantity=F("stock_quantity") + item.quantity,
            )
        else:
            Product.objects.filter(pk=item.product_id).update(
                stock_quantity=F("stock_quantity") + item.quantity,
            )
        product_ids.add(item.product_id)

    for product in Product.objects.filter(pk__in=product_ids):
        product.refresh_stock_status()

    payment.inventory_released_at = timezone.now()
    return True
