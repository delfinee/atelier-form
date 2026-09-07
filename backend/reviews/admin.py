from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["product", "user", "rating", "is_published", "is_verified_purchase", "created_at"]
    list_filter = ["rating", "is_published"]
    search_fields = ["product__name", "user__email", "title", "body"]
