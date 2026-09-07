from django.contrib import admin
from django.utils.html import format_html

from .models import SiteImage


@admin.register(SiteImage)
class SiteImageAdmin(admin.ModelAdmin):
    list_display = ("name", "preview", "ratio", "dimensions", "kilobytes", "license", "creator")
    list_filter = ("ratio", "license", "provider")
    search_fields = ("name", "alt_text", "creator", "source_title", "search_query")
    readonly_fields = ("preview", "checksum", "byte_size", "width", "height", "fetched_at")
    # `data` is excluded deliberately: rendering a megabyte of bytea into a
    # textarea would hang the change form and offers nothing editable.
    exclude = ("data",)

    def has_add_permission(self, request):
        """Images arrive through `manage.py fetch_images`, never by hand.

        `data` is excluded from this form, so an admin-created row would have no
        bytes and fail the NOT NULL constraint with a confusing error.
        """
        return False

    @admin.display(description="Preview")
    def preview(self, obj):
        if not obj.pk:
            return "—"
        return format_html('<img src="{}" style="height:70px;border-radius:4px" alt="">', obj.url)

    @admin.display(description="Size")
    def dimensions(self, obj):
        return f"{obj.width}×{obj.height}"

    @admin.display(description="Weight", ordering="byte_size")
    def kilobytes(self, obj):
        return f"{obj.byte_size / 1024:.0f} KB"
