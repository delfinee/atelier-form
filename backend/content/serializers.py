"""Journal, FAQ, newsletter and contact serializers."""

from rest_framework import serializers

from .models import FAQ, Article, ContactMessage, FAQGroup, NewsletterSubscriber


class ArticleListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ["uuid", "slug", "title", "standfirst", "category", "author",
                  "cover_image", "read_time", "is_featured", "published_at"]
        read_only_fields = fields


class ArticleDetailSerializer(ArticleListSerializer):
    class Meta(ArticleListSerializer.Meta):
        fields = ArticleListSerializer.Meta.fields + ["body"]
        read_only_fields = fields


class FAQSerializer(serializers.ModelSerializer):
    group = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = FAQ
        fields = ["id", "group", "question", "answer", "sort_order"]
        read_only_fields = fields


class FAQGroupSerializer(serializers.ModelSerializer):
    items = FAQSerializer(many=True, read_only=True)

    class Meta:
        model = FAQGroup
        fields = ["slug", "title", "blurb", "sort_order", "items"]
        read_only_fields = fields


class NewsletterSerializer(serializers.Serializer):
    """Plain serializer on purpose.

    A ModelSerializer would attach a UniqueValidator to `email` and reject a
    repeat subscription with a 400 -- which both leaks who is already on the
    list and prevents reactivating a dormant record.
    """

    email = serializers.EmailField()


class ContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ["uuid", "name", "email", "subject", "order_number", "message", "created_at"]
        read_only_fields = ["uuid", "created_at"]
