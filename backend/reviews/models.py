"""Product reviews.

Included because the charter names `reviews` as one of the five modular apps.
Published reviews render on product pages, and only a user with a paid order
line for the product can create one.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from config.mixins import TimeStampedModel, UUIDModel


class Review(UUIDModel, TimeStampedModel):
    product = models.ForeignKey("products.Product", related_name="reviews", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="reviews", on_delete=models.CASCADE)
    order_item = models.ForeignKey("orders.OrderItem", null=True, blank=True,
                                   related_name="reviews", on_delete=models.SET_NULL,
                                   help_text="Set when the review follows a verified purchase.")

    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=160, blank=True)
    body = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["product", "user"], name="one_review_per_product_per_user"),
        ]
        indexes = [models.Index(fields=["product", "is_published"])]

    def __str__(self):
        return f"{self.rating}★ {self.product.name}"

    @property
    def is_verified_purchase(self) -> bool:
        return self.order_item_id is not None
