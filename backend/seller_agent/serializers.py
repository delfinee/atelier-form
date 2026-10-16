from rest_framework import serializers


class MessageInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    text = serializers.CharField(max_length=2000)


class ChangeInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=["stock", "price", "listing", "fulfillment"])
    target = serializers.CharField(max_length=200, required=False, default="", allow_blank=True)
    values = serializers.DictField()


class ConfirmInput(serializers.Serializer):
    confirmed = serializers.BooleanField()

    def validate_confirmed(self, value):
        if value is not True:
            raise serializers.ValidationError("Explicit confirmation is required.")
        return value


class InventoryInput(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0, max_value=1000000)
    variant = serializers.UUIDField(required=False, allow_null=True, default=None)


class PriceInput(serializers.Serializer):
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    variant = serializers.UUIDField(required=False, allow_null=True, default=None)


class FulfillmentInput(serializers.Serializer):
    carrier = serializers.CharField(max_length=80)
    tracking_number = serializers.RegexField(r"^[A-Za-z0-9-]{6,80}$")
    status = serializers.ChoiceField(choices=["fulfilled"], default="fulfilled")


class ListingInput(serializers.Serializer):
    name = serializers.CharField(max_length=180)
    category = serializers.SlugField()
    description = serializers.CharField(max_length=6000)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    quantity = serializers.IntegerField(min_value=0, max_value=1000000)
