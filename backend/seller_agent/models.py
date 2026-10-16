from django.conf import settings
from django.db import models
from config.mixins import TimeStampedModel, UUIDModel


class Conversation(UUIDModel, TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    context = models.JSONField(default=dict)


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
