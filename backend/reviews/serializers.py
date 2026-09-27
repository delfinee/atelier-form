"""Public review representation; authorship and verification are server-owned."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from products.models import Product

from .models import Review
from .validators import validate_review_text


class ReviewTextField(serializers.CharField):
    def __init__(self, *args, multiline=False, **kwargs):
        self.multiline = multiline
        super().__init__(*args, **kwargs)

    def run_validation(self, data=serializers.empty):
        # CharField's blank shortcut strips input before to_internal_value().
        if isinstance(data, str):
            try:
                validate_review_text(data, multiline=self.multiline)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages, code=exc.code) from exc
        return super().run_validation(data)


class ReviewSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(slug_field="slug", queryset=Product.objects.active())
    author = serializers.CharField(source="public_author", read_only=True)
    is_verified_purchase = serializers.BooleanField(read_only=True)
    title = ReviewTextField(required=False, allow_blank=True,
                            max_length=Review._meta.get_field("title").max_length)
    body = ReviewTextField(required=False, allow_blank=True, multiline=True)

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
