from .text import text
from rest_framework import serializers
from orders.models import DeliveryMethod
from orders.serializers import AddressInputSerializer


class LineInput(serializers.Serializer):
    product = serializers.SlugField(max_length=200)
    variant = serializers.UUIDField(required=False, allow_null=True, default=None)
    quantity = serializers.IntegerField(min_value=1, max_value=99)


class DraftInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    lines = LineInput(many=True, allow_empty=False, max_length=20)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=32, allow_blank=True, default="")
    shipping_address = AddressInputSerializer()
    delivery_method = serializers.ChoiceField(choices=DeliveryMethod.choices, default="standard")


class ChatInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    text = serializers.CharField(max_length=2000)


class ActionInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["confirm", "pay", "pack", "packed", "ship"])
    confirmed = serializers.BooleanField(default=False)
    carrier = serializers.CharField(max_length=80, required=False)
    tracking_number = serializers.RegexField(r"^[A-Za-z0-9-]{6,100}$", required=False)

    def validate(self, attrs):
        if attrs["action"] == "confirm" and not attrs["confirmed"]:
            raise serializers.ValidationError(text("请先明确确认商品、金额和收货信息。", "Please confirm the products, total and delivery details first."))
        if attrs["action"] == "ship" and not all(attrs.get(k) for k in ["carrier", "tracking_number"]):
            raise serializers.ValidationError(text("发货需要物流公司和有效运单号。", "A carrier and valid tracking number are required to ship."))
        return attrs
