"""Payment records.

No card data is ever accepted or stored -- not a number, not a CVV, not an
expiry. A real provider will be handed the order and will return a session id
and a webhook; those are the only things this table holds.
"""

from decimal import Decimal

from django.db import models

from config.mixins import TimeStampedModel, UUIDModel


class PaymentProviderChoices(models.TextChoices):
    MOCK = "mock", "Mock (development)"
    STRIPE_WECHAT = "stripe_wechat", "Stripe — WeChat Pay"


class PaymentState(models.TextChoices):
    CREATED = "created", "Created"
    REQUIRES_ACTION = "requires_action", "Requires customer action"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"


class Payment(UUIDModel, TimeStampedModel):
    order = models.ForeignKey("orders.Order", related_name="payments", on_delete=models.CASCADE)
    provider = models.CharField(max_length=32, choices=PaymentProviderChoices.choices,
                                default=PaymentProviderChoices.MOCK)
    state = models.CharField(max_length=20, choices=PaymentState.choices,
                             default=PaymentState.CREATED, db_index=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="CNY")

    # Provider-side identifiers. Opaque strings, never credentials.
    provider_session_id = models.CharField(max_length=200, blank=True, db_index=True)
    provider_payment_id = models.CharField(max_length=200, blank=True)
    checkout_url = models.TextField(blank=True, default="")
    failure_reason = models.CharField(max_length=200, blank=True)
    inventory_released_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Set once when a failed/expired payment returns reserved stock.",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.provider} {self.state} for {self.order.order_number}"
