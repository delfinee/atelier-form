"""Serializers for buyer-seller messaging."""

from rest_framework import serializers

from .models import Conversation, ConversationMessage


class ConversationMessageSerializer(serializers.ModelSerializer):
    conversation_uuid = serializers.UUIDField(source="conversation.uuid", read_only=True)
    sender_name = serializers.SerializerMethodField()
    is_sender = serializers.SerializerMethodField()
    is_buyer = serializers.SerializerMethodField()
    is_seller = serializers.SerializerMethodField()

    class Meta:
        model = ConversationMessage
        fields = [
            "uuid",
            "conversation_uuid",
            "sender_id",
            "sender_name",
            "is_sender",
            "is_buyer",
            "is_seller",
            "body",
            "created_at",
            "read_at",
        ]
        read_only_fields = [
            "uuid",
            "conversation_uuid",
            "sender_id",
            "sender_name",
            "is_sender",
            "is_buyer",
            "is_seller",
            "created_at",
            "read_at",
        ]

    def get_sender_name(self, obj):
        if obj.sender.get_full_name():
            return obj.sender.get_full_name()
        return obj.sender.email.split("@")[0]

    def get_is_sender(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.sender_id == request.user.id
        return False

    def get_is_buyer(self, obj):
        return obj.sender_id == obj.conversation.buyer_id

    def get_is_seller(self, obj):
        maker = obj.conversation.maker
        return bool(maker and maker.owner_id and obj.sender_id == maker.owner_id)


class ConversationSerializer(serializers.ModelSerializer):
    buyer_name = serializers.SerializerMethodField()
    maker_name = serializers.CharField(source="maker.name", read_only=True)
    maker_slug = serializers.CharField(source="maker.slug", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True, allow_null=True)
    product_slug = serializers.CharField(source="product.slug", read_only=True, allow_null=True)
    product_price = serializers.SerializerMethodField()
    order_number = serializers.CharField(source="order.order_number", read_only=True, allow_null=True)
    latest_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "uuid",
            "buyer_id",
            "buyer_name",
            "maker_id",
            "maker_name",
            "maker_slug",
            "product_id",
            "product_name",
            "product_slug",
            "product_price",
            "order_id",
            "order_number",
            "is_closed",
            "created_at",
            "updated_at",
            "latest_message",
            "unread_count",
        ]
        read_only_fields = fields

    def get_buyer_name(self, obj):
        if obj.buyer.get_full_name():
            return obj.buyer.get_full_name()
        return obj.buyer.email.split("@")[0]

    def get_product_price(self, obj):
        if obj.product:
            return str(obj.product.price)
        return None

    def get_latest_message(self, obj):
        last_msg = obj.messages.order_by("-created_at").first()
        if last_msg:
            return {
                "uuid": str(last_msg.uuid),
                "body": last_msg.body,
                "sender_id": last_msg.sender_id,
                "created_at": last_msg.created_at.isoformat(),
            }
        return None

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.messages.filter(read_at__isnull=True).exclude(sender=request.user).count()
        return 0


class CreateConversationSerializer(serializers.Serializer):
    maker = serializers.CharField(required=False, allow_blank=True)
    product = serializers.CharField(required=False, allow_blank=True)
    order = serializers.CharField(required=False, allow_blank=True)


class SendMessageSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=3000, required=True, allow_blank=False)
