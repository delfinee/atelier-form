"""Customer capabilities are separate from seller logins and legacy Mini sessions."""
from django.conf import settings
from django.db import models
from config.mixins import TimeStampedModel, UUIDModel


class CustomerSession(UUIDModel, TimeStampedModel):
    conversation = models.OneToOneField("concierge.Conversation", on_delete=models.CASCADE,
                                        related_name="customer_access")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    revoked = models.BooleanField(default=False)


class SellerReply(TimeStampedModel):
    conversation = models.ForeignKey("concierge.Conversation", on_delete=models.CASCADE,
                                     related_name="seller_replies")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    text = models.CharField(max_length=2000)

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["conversation", "request_id"],
                                               name="seller_reply_once")]


class CustomerAction(TimeStampedModel):
    """Preserve who initiated an action when the shared commerce service runs it."""
    session = models.ForeignKey(CustomerSession, on_delete=models.PROTECT)
    draft = models.ForeignKey("concierge.OrderDraft", on_delete=models.PROTECT,
                              related_name="customer_actions")
    action = models.CharField(max_length=20)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["draft", "action"], name="customer_action_once")]
