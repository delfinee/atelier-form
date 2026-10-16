"""Seller-scoped records for the simulated WeChat customer-service desk."""
import uuid

from django.conf import settings
from django.db import models
from config.mixins import TimeStampedModel, UUIDModel


class Conversation(UUIDModel, TimeStampedModel):
    maker = models.ForeignKey("products.Maker", on_delete=models.PROTECT)
    customer_label = models.CharField(max_length=80, default="模拟微信客户")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="customer_service_conversations")


class Message(TimeStampedModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    request_id = models.UUIDField(default=uuid.uuid4)
    text = models.CharField(max_length=2000)
    response = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "request_id"], name="concierge_message_once")]
        ordering = ["id"]


class OrderDraft(UUIDModel, TimeStampedModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.PROTECT, related_name="drafts")
    request_id = models.UUIDField(default=uuid.uuid4)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    lines = models.JSONField()
    customer = models.JSONField()
    delivery_method = models.CharField(max_length=20, default="standard")
    total = models.DecimalField(max_digits=10, decimal_places=2)
    shipping = models.DecimalField(max_digits=10, decimal_places=2)
    expires_at = models.DateTimeField()
    order = models.OneToOneField("orders.Order", null=True, blank=True, on_delete=models.PROTECT)
    payment = models.OneToOneField("payments.Payment", null=True, blank=True, on_delete=models.PROTECT)
    packing_started_at = models.DateTimeField(null=True, blank=True)
    packed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "request_id"], name="concierge_draft_once")]


class Event(TimeStampedModel):
    draft = models.ForeignKey(OrderDraft, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)

    class Meta:
        ordering = ["id"]
