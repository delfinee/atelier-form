from django.contrib import admin

from .models import FAQ, Article, ContactMessage, FAQGroup, NewsletterSubscriber


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "author", "is_published", "is_featured", "published_at"]
    list_filter = ["is_published", "is_featured", "category"]
    search_fields = ["title", "standfirst", "author"]
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_at"


class FAQInline(admin.TabularInline):
    model = FAQ
    extra = 1


@admin.register(FAQGroup)
class FAQGroupAdmin(admin.ModelAdmin):
    list_display = ["title", "slug", "sort_order", "is_active"]
    prepopulated_fields = {"slug": ("title",)}
    inlines = [FAQInline]


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ["question", "group", "sort_order", "is_active"]
    list_filter = ["group", "is_active"]
    search_fields = ["question", "answer"]


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ["email", "is_active", "subscribed_at", "source"]
    list_filter = ["is_active", "source"]
    search_fields = ["email"]


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "subject", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["name", "email", "subject", "message"]
    readonly_fields = ["uuid", "created_at", "updated_at"]
