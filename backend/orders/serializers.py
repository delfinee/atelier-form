"""Cart, checkout and order serializers.

Note what the write serializers deliberately do *not* accept: any price, any
total, any stock figure, and any card detail. Those are server-side facts.
"""

from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Cart, CartItem, DeliveryMethod, Order, OrderItem


class CartItemSerializer(serializers.ModelSerializer):
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    variant_label = serializers.CharField(source="variant.label", read_only=True, default="")
    variant_uuid = serializers.UUIDField(source="variant.uuid", read_only=True, default=None)
    image = serializers.SerializerMethodField()
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    available_quantity = serializers.IntegerField(read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "product_slug", "product_name", "variant_uuid", "variant_label",
                  "image", "quantity", "unit_price", "line_total", "available_quantity"]
        read_only_fields = fields

    def get_image(self, obj) -> str:
        first = obj.product.product_images.all()[:1]
        return first[0].url if first else ""


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    shipping = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Cart
        fields = ["uuid", "items", "item_count", "subtotal", "shipping", "total", "updated_at"]
        read_only_fields = fields

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_shipping(self, obj) -> Decimal:
        return obj.shipping_amount()

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_total(self, obj) -> Decimal:
        return obj.total()


class AddToCartSerializer(serializers.Serializer):
    product_slug = serializers.CharField()
    variant = serializers.CharField(required=False, allow_blank=True, allow_null=True,
                                    help_text="Variant UUID, or its label.")
    quantity = serializers.IntegerField(min_value=1, max_value=99, default=1)


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0, max_value=99)


class AddressInputSerializer(serializers.Serializer):
    """A delivery address supplied at checkout, or referenced by uuid."""

    label = serializers.CharField(required=False, allow_blank=True, default="Delivery")
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    address_line_1 = serializers.CharField(max_length=200)
    address_line_2 = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    city = serializers.CharField(max_length=100)
    state_region = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    postal_code = serializers.CharField(max_length=20)
    country = serializers.CharField(max_length=80, default="China")
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")


class CheckoutSerializer(serializers.Serializer):
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    delivery_method = serializers.ChoiceField(choices=DeliveryMethod.choices,
                                              default=DeliveryMethod.STANDARD)
    gift_note = serializers.CharField(required=False, allow_blank=True, default="")

    # Either a saved address...
    shipping_address_uuid = serializers.UUIDField(required=False, allow_null=True)
    # ...or a new one supplied inline.
    shipping_address = AddressInputSerializer(required=False, allow_null=True)
    save_address = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if not attrs.get("shipping_address_uuid") and not attrs.get("shipping_address"):
            raise serializers.ValidationError(
                {"shipping_address": "Provide either shipping_address_uuid or shipping_address."})
        return attrs


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["id", "product_slug", "product_name", "variant_name", "sku",
                  "image", "unit_price", "quantity", "line_total"]
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_label = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = ["uuid", "order_number", "status", "status_label", "payment_status",
                  "fulfillment_status", "subtotal", "shipping_amount", "discount_amount",
                  "total", "currency", "customer_email", "delivery_method",
                  "shipping_address_snapshot", "carrier", "tracking_number",
                  "placed_at", "items"]
        read_only_fields = fields


class AdminOrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["status", "payment_status", "fulfillment_status", "carrier", "tracking_number"]


class SellerOrderItemSerializer(OrderItemSerializer):
    class Meta(OrderItemSerializer.Meta):
        fields = OrderItemSerializer.Meta.fields + ["maker_name"]


class SellerOrderSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    seller_subtotal = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["uuid", "order_number", "status", "payment_status", "fulfillment_status",
                  "customer_email", "customer_phone", "shipping_address_snapshot",
                  "carrier", "tracking_number", "placed_at", "seller_subtotal", "items"]
        read_only_fields = fields

    def _seller_items(self, obj):
        return obj.items.filter(maker__owner=self.context["request"].user)

    @extend_schema_field(SellerOrderItemSerializer(many=True))
    def get_items(self, obj):
        return SellerOrderItemSerializer(self._seller_items(obj), many=True).data

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_seller_subtotal(self, obj):
        return sum((item.line_total for item in self._seller_items(obj)), Decimal("0.00"))
