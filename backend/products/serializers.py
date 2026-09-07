"""Catalogue serializers."""

from rest_framework import serializers

from .models import Category, Collection, Maker, Product, ProductImage, ProductVariant


class ProductImageSerializer(serializers.ModelSerializer):
    url = serializers.CharField(read_only=True)

    class Meta:
        model = ProductImage
        fields = ["id", "image", "url", "alt_text", "sort_order", "is_primary"]


class ProductVariantSerializer(serializers.ModelSerializer):
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    available = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = ["uuid", "group", "label", "sku", "swatch", "unit_price",
                  "price_override", "stock_quantity", "available", "is_active", "sort_order"]
        read_only_fields = ["uuid"]


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Category
        fields = ["uuid", "name", "slug", "tagline", "description",
                  "hero_image", "tile_image", "sort_order", "is_active", "product_count"]
        read_only_fields = ["uuid"]


class CollectionSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Collection
        fields = ["uuid", "name", "slug", "tagline", "description", "story",
                  "hero_image", "tile_image", "is_featured", "is_active",
                  "sort_order", "product_count"]
        read_only_fields = ["uuid"]


class MakerListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Maker
        fields = ["uuid", "name", "slug", "discipline", "location", "since",
                  "tagline", "portrait", "is_featured"]
        read_only_fields = ["uuid"]


class MakerDetailSerializer(MakerListSerializer):
    class Meta(MakerListSerializer.Meta):
        fields = MakerListSerializer.Meta.fields + ["short_bio", "biography", "process", "studio_images"]


class ProductListSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    maker = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    maker_name = serializers.CharField(source="maker.name", read_only=True)
    primary_image = serializers.SerializerMethodField()
    material_families = serializers.ListField(read_only=True)

    class Meta:
        model = Product
        fields = ["uuid", "slug", "name", "short_description", "price", "currency",
                  "category", "maker", "maker_name", "materials", "material_families",
                  "is_featured", "is_new_arrival", "stock_status", "primary_image"]
        read_only_fields = fields

    def get_primary_image(self, obj) -> str:
        image = obj.product_images.all()[:1]
        return image[0].url if image else ""


class ProductDetailSerializer(ProductListSerializer):
    images = ProductImageSerializer(source="product_images", many=True, read_only=True)
    variants = ProductVariantSerializer(source="product_variants", many=True, read_only=True)
    collections = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    available_quantity = serializers.IntegerField(read_only=True)

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            "description", "story", "dimensions", "care_instructions",
            "shipping_information", "collections", "images", "variants",
            "is_made_to_order", "available_quantity",
        ]
        read_only_fields = fields


# -- admin write serializers ---------------------------------------------

class AdminProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "uuid", "slug", "name", "short_description", "description", "story",
            "price", "currency", "category", "maker", "collections", "materials",
            "dimensions", "care_instructions", "shipping_information",
            "is_active", "is_featured", "is_new_arrival", "is_made_to_order",
            "stock_quantity", "stock_status", "sort_weight",
        ]
        read_only_fields = ["uuid", "stock_status"]


class SellerProductSerializer(AdminProductSerializer):
    """Product writes with maker ownership fixed by the authenticated seller."""

    maker = MakerListSerializer(read_only=True)

    class Meta(AdminProductSerializer.Meta):
        read_only_fields = ["uuid", "stock_status", "maker"]


class AdminStockSerializer(serializers.Serializer):
    """Absolute stock level, not a delta -- an idempotent adjustment."""

    stock_quantity = serializers.IntegerField(min_value=0)
    variant_uuid = serializers.UUIDField(required=False, allow_null=True)
