"""Data models for buyer-seller threaded messaging."""

from django.conf import settings
from django.db import models

from config.mixins import TimeStampedModel, UUIDModel


class Conversation(UUIDModel, TimeStampedModel):
    """Threaded conversation between an authenticated buyer and an artisan maker."""

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="buyer_conversations",
    )
    maker = models.ForeignKey(
        "products.Maker",
        on_delete=models.CASCADE,
        related_name="maker_conversations",
    )
    product = models.ForeignKey(
        "products.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conversations",
    )
    order = models.ForeignKey(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conversations",
    )
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["buyer", "-updated_at"]),
            models.Index(fields=["maker", "-updated_at"]),
        ]

    def __str__(self):
        return f"Conversation {self.uuid} ({self.buyer} <-> {self.maker.name})"


class ConversationMessage(UUIDModel, TimeStampedModel):
    """An individual message in a conversation thread."""

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_messages",
    )
    body = models.TextField(max_length=3000)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
        ]

    def __str__(self):
        return f"Message {self.uuid} by {self.sender_id}"
