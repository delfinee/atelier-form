from django.conf import settings
from django.db import models
from config.mixins import TimeStampedModel, UUIDModel


class Conversation(UUIDModel, TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    context = models.JSONField(default=dict)
    language = models.CharField(max_length=16, default='en')


class Message(TimeStampedModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    request_id = models.UUIDField()
    text = models.CharField(max_length=2000)
    channel = models.CharField(max_length=16)
    response = models.JSONField(default=dict)

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["conversation", "request_id"], name="seller_agent_message_once")]


class Change(UUIDModel, TimeStampedModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.PROTECT, related_name="changes")
    request_id = models.UUIDField()
    action = models.CharField(max_length=32)
    target = models.CharField(max_length=200, blank=True)
    values = models.JSONField()
    before = models.JSONField()
    status = models.CharField(max_length=16, default="pending")
    expires_at = models.DateTimeField()
    result = models.JSONField(default=dict)
    confirmed_channel = models.CharField(max_length=16, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "request_id"], name="seller_agent_change_once")]


class SellerOperation(UUIDModel, TimeStampedModel):
    """Immutable attribution for a successful seller write, separate from ownership."""
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name='seller_operations')
    actor_name = models.CharField(max_length=200)
    action = models.CharField(max_length=32)
    channel = models.CharField(max_length=16)
    product = models.ForeignKey('products.Product', null=True, blank=True,
                                on_delete=models.SET_NULL, related_name='seller_operations')
    order = models.ForeignKey('orders.Order', null=True, blank=True,
                              on_delete=models.SET_NULL, related_name='seller_operations')
    product_slug = models.CharField(max_length=200, blank=True)
    order_number = models.CharField(max_length=80, blank=True)
    change = models.OneToOneField(Change, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name='operation')

    class Meta:
        ordering = ['-created_at', '-pk']


class WechatIdentity(UUIDModel, TimeStampedModel):
    app_id = models.CharField(max_length=80)
    openid_hash = models.CharField(max_length=64)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    mode = models.CharField(max_length=16, default="wechat")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["app_id", "openid_hash"], name="seller_wechat_identity_once")]


class WechatSession(TimeStampedModel):
    identity = models.ForeignKey(WechatIdentity, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)


class LinkTicket(UUIDModel, TimeStampedModel):
    identity = models.ForeignKey(WechatIdentity, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class UsedLoginCode(models.Model):
    code_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()


class ProviderSecret(TimeStampedModel):
    """Server-only encrypted configuration; never included in API serializers."""
    provider = models.CharField(max_length=32, primary_key=True)
    encrypted_key = models.TextField()
