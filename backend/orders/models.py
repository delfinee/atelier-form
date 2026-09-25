"""Carts and orders.

Carts are mutable and hold references. Orders are immutable records that hold
*snapshots*: an order placed last year must still show the name and price it was
bought at, even if the product is renamed or repriced afterwards.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from config.mixins import TimeStampedModel, UUIDModel

ZERO = Decimal("0.00")


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    PROCESSING = "processing", "Processing"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


class PaymentStatus(models.TextChoices):
    UNPAID = "unpaid", "Unpaid"
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"


class FulfillmentStatus(models.TextChoices):
    UNFULFILLED = "unfulfilled", "Unfulfilled"
    PARTIAL = "partial", "Partially fulfilled"
    FULFILLED = "fulfilled", "Fulfilled"


class DeliveryMethod(models.TextChoices):
    STANDARD = "standard", "Standard delivery"
    EXPRESS = "express", "Express delivery"


# -- Cart -----------------------------------------------------------------

class Cart(UUIDModel, TimeStampedModel):
    """One open cart per user, or per anonymous session."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="carts",
                             null=True, blank=True, on_delete=models.CASCADE)
    session_key = models.CharField(max_length=64, blank=True, db_index=True,
                                   help_text="Anonymous owner, when there is no user.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["user"], condition=models.Q(is_active=True, user__isnull=False),
                                    name="one_active_cart_per_user"),
            models.UniqueConstraint(fields=["session_key"],
                                    condition=models.Q(is_active=True, user__isnull=True),
                                    name="one_active_cart_per_session"),
            models.CheckConstraint(
                condition=models.Q(user__isnull=False) | ~models.Q(session_key=""),
                name="cart_has_an_owner",
            ),
        ]

    def __str__(self):
        return f"Cart {self.uuid} ({self.user or self.session_key})"

    # -- totals: always computed here, never accepted from a client --------
    @property
    def line_items(self):
        return self.items.select_related("product", "variant", "product__category", "product__maker")

    @property
    def subtotal(self) -> Decimal:
        return sum((item.line_total for item in self.line_items), ZERO)

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items.all())

    def shipping_amount(self, method: str = DeliveryMethod.STANDARD) -> Decimal:
        if not self.items.exists():
            return ZERO
        if method == DeliveryMethod.EXPRESS:
            return Decimal(settings.COMMERCE["SHIPPING_EXPRESS"])
        threshold = Decimal(settings.COMMERCE["FREE_SHIPPING_THRESHOLD"])
        if self.subtotal >= threshold:
            return ZERO
        return Decimal(settings.COMMERCE["SHIPPING_STANDARD"])

    def total(self, method: str = DeliveryMethod.STANDARD) -> Decimal:
        return self.subtotal + self.shipping_amount(method)


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey("products.Product", related_name="cart_items", on_delete=models.CASCADE)
    variant = models.ForeignKey("products.ProductVariant", related_name="cart_items",
                                null=True, blank=True, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product", "variant"],
                                    name="unique_cart_line_with_variant"),
            models.UniqueConstraint(fields=["cart", "product"], condition=models.Q(variant__isnull=True),
                                    name="unique_cart_line_without_variant"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="cart_quantity_positive"),
        ]

    def __str__(self):
        return f"{self.quantity} × {self.product.name}"

    @property
    def unit_price(self) -> Decimal:
        """Read from the database every time. The client never sets a price."""
        return self.variant.unit_price if self.variant else self.product.price

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity

    @property
    def available_quantity(self) -> int:
        if self.product.is_made_to_order:
            return 10**6
        return self.variant.stock_quantity if self.variant else self.product.stock_quantity


# -- Orders ---------------------------------------------------------------

class OrderNumberSequence(models.Model):
    """Gap-free, per-year order numbering.

    A dedicated row locked with `select_for_update` rather than `COUNT(*) + 1`,
    which would hand two concurrent checkouts the same number.
    """

    year = models.PositiveIntegerField(primary_key=True)
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = "order number sequences"

    @classmethod
    def next_number(cls, year: int | None = None) -> str:
        year = year or timezone.now().year
        with transaction.atomic():
            row, _ = cls.objects.select_for_update().get_or_create(year=year)
            row.last_value += 1
            row.save(update_fields=["last_value"])
        prefix = settings.COMMERCE["ORDER_NUMBER_PREFIX"]
        return f"{prefix}-{year}-{row.last_value:06d}"


class Order(UUIDModel, TimeStampedModel):
    order_number = models.CharField(max_length=32, unique=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="orders",
                             null=True, blank=True, on_delete=models.SET_NULL)

    status = models.CharField(max_length=20, choices=OrderStatus.choices,
                              default=OrderStatus.PENDING, db_index=True)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices,
                                      default=PaymentStatus.UNPAID, db_index=True)
    fulfillment_status = models.CharField(max_length=20, choices=FulfillmentStatus.choices,
                                          default=FulfillmentStatus.UNFULFILLED)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    shipping_amount = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    currency = models.CharField(max_length=3, default="CNY")

    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=32, blank=True)

    # Snapshots, not foreign keys: editing an address must not rewrite history.
    shipping_address_snapshot = models.JSONField(default=dict)
    billing_address_snapshot = models.JSONField(default=dict, blank=True)

    delivery_method = models.CharField(max_length=20, choices=DeliveryMethod.choices,
                                       default=DeliveryMethod.STANDARD)
    carrier = models.CharField(max_length=80, blank=True)
    tracking_number = models.CharField(max_length=80, blank=True)
    gift_note = models.TextField(blank=True)
    placed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-placed_at"]
        indexes = [
            models.Index(fields=["user", "-placed_at"]),
            models.Index(fields=["status", "-placed_at"]),
        ]

    def __str__(self):
        return self.order_number

    # -- frontend template compatibility ---------------------------------
    @property
    def id_display(self) -> str:
        return self.order_number

    @property
    def status_label(self) -> str:
        return {
            OrderStatus.PENDING: "Awaiting confirmation",
            OrderStatus.CONFIRMED: "Confirmed",
            OrderStatus.PROCESSING: "Being made",
            OrderStatus.SHIPPED: "On its way",
            OrderStatus.DELIVERED: "Delivered",
            OrderStatus.CANCELLED: "Cancelled",
        }.get(self.status, self.get_status_display())

    @property
    def shipping(self) -> Decimal:
        return self.shipping_amount

    @property
    def date(self) -> str:
        return f"{self.placed_at.day} {self.placed_at.strftime('%B %Y')}"

    @property
    def address(self) -> dict:
        """Shape the snapshot the way the delivery block expects."""
        snap = self.shipping_address_snapshot or {}
        return {
            "name": f"{snap.get('first_name', '')} {snap.get('last_name', '')}".strip(),
            "line1": snap.get("address_line_1", ""),
            "line2": snap.get("address_line_2", ""),
            "city": snap.get("city", ""),
            "postcode": snap.get("postal_code", ""),
            "country": snap.get("country", ""),
            "phone": snap.get("phone", ""),
            "label": snap.get("label", ""),
        }

    @property
    def estimated(self) -> str:
        if self.status == OrderStatus.DELIVERED:
            return f"Delivered {self.placed_at.day} {self.placed_at.strftime('%B')}"
        return "Arriving within 3–6 working days"

    @property
    def timeline(self) -> list:
        """Progress steps for the order-detail page."""
        order = [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PROCESSING,
                 OrderStatus.SHIPPED, OrderStatus.DELIVERED]
        if self.status == OrderStatus.CANCELLED:
            return [{"label": "Order placed", "date": self.date, "done": True},
                    {"label": "Cancelled", "date": f"{self.updated_at.day} {self.updated_at.strftime('%b')}",
                     "done": True}]
        reached = order.index(self.status) if self.status in order else 0
        labels = ["Order placed", "Confirmed", "Made & packed", "Dispatched", "Delivered"]
        return [{"label": label,
                 "date": f"{self.placed_at.day} {self.placed_at.strftime('%b')}" if i <= reached else "Expected",
                 "done": i <= reached}
                for i, label in enumerate(labels)]

    def recalculate(self, save: bool = True):
        """Totals are always derived from the stored line snapshots."""
        self.subtotal = sum((item.line_total for item in self.items.all()), ZERO)
        self.total = self.subtotal + self.shipping_amount - self.discount_amount
        if save:
            self.save(update_fields=["subtotal", "total", "updated_at"])
        return self.total


class OrderItem(TimeStampedModel):
    """An immutable snapshot of what was bought.

    `product`/`variant` are SET_NULL references kept only for reporting -- every
    value the customer sees is copied here at checkout.
    """

    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey("products.Product", related_name="order_items",
                                null=True, blank=True, on_delete=models.SET_NULL)
    variant = models.ForeignKey("products.ProductVariant", related_name="order_items",
                                null=True, blank=True, on_delete=models.SET_NULL)
    maker = models.ForeignKey("products.Maker", related_name="order_items",
                              null=True, blank=True, on_delete=models.SET_NULL)

    sku = models.CharField(max_length=64, blank=True)
    product_slug = models.CharField(max_length=180, blank=True)
    product_name = models.CharField(max_length=160)
    maker_name = models.CharField(max_length=160, blank=True)
    variant_name = models.CharField(max_length=80, blank=True)
    image = models.CharField(max_length=200, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="order_quantity_positive"),
        ]

    def __str__(self):
        return f"{self.quantity} × {self.product_name}"

    # -- frontend template compatibility ---------------------------------
    @property
    def name(self) -> str:
        return self.product_name

    @property
    def variant_label(self) -> str:
        return self.variant_name

    @property
    def price(self):
        return self.unit_price

    @property
    def qty(self) -> int:
        return self.quantity

    @property
    def slug(self) -> str:
        return self.product_slug


class SellerFulfillment(UUIDModel, TimeStampedModel):
    """One seller's independent slice of an Order's fulfilment.

    Membership is derived, not stored: the lines belonging to this fulfilment
    are `OrderItem.objects.filter(order=self.order, maker=self.maker)` -- the
    same (order, maker) pair that already identifies seller ownership on
    OrderItem, so there is no second, potentially-inconsistent membership list
    to maintain (see `items` below).
    """

    order = models.ForeignKey(Order, related_name="seller_fulfillments", on_delete=models.CASCADE)
    maker = models.ForeignKey("products.Maker", related_name="seller_fulfillments",
                              on_delete=models.PROTECT)

    status = models.CharField(max_length=20, choices=FulfillmentStatus.choices,
                              default=FulfillmentStatus.UNFULFILLED)
    carrier = models.CharField(max_length=80, blank=True)
    tracking_number = models.CharField(max_length=80, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order_id", "maker__name"]
        constraints = [
            models.UniqueConstraint(fields=["order", "maker"], name="unique_fulfillment_per_order_maker"),
        ]

    def __str__(self):
        return f"{self.order.order_number} · {self.maker.name} ({self.status})"

    @property
    def items(self):
        """The purchased lines this seller is responsible for within the order."""
        return self.order.items.filter(maker=self.maker)
