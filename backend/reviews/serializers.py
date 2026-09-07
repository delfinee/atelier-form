"""Public review representation; authorship and verification are server-owned."""

from rest_framework import serializers

from products.models import Product

from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(slug_field="slug", queryset=Product.objects.active())
    author = serializers.CharField(source="user.full_name", read_only=True)
    is_verified_purchase = serializers.BooleanField(read_only=True)

    class Meta:
        model = Review
        fields = ["uuid", "product", "author", "rating", "title", "body",
                  "is_verified_purchase", "created_at"]
        read_only_fields = ["uuid", "author", "is_verified_purchase", "created_at"]

    def validate(self, attrs):
        user = self.context["request"].user
        product = attrs.get("product") or getattr(self.instance, "product", None)
        if self.instance is not None and product != self.instance.product:
            raise serializers.ValidationError({"product": "A review cannot be moved to another product."})
        if self.instance is None and Review.objects.filter(user=user, product=product).exists():
            raise serializers.ValidationError({"detail": "You have already reviewed this product."})
        return attrs
