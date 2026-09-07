from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Address, User, WishlistItem


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Email-based admin: there is no username field on this model."""

    ordering = ["-date_joined"]
    list_display = ["email", "first_name", "last_name", "is_seller", "is_admin",
                    "is_staff", "is_active", "date_joined"]
    list_filter = ["is_seller", "is_admin", "is_staff", "is_active", "accepts_marketing"]
    search_fields = ["email", "first_name", "last_name"]
    readonly_fields = ["uuid", "date_joined", "last_login", "created_at", "updated_at"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("first_name", "last_name", "phone", "accepts_marketing")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_admin", "is_seller", "is_superuser",
                                    "groups", "user_permissions")}),
        ("Dates", {"fields": ("uuid", "last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "password1", "password2")}),
    )


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ["label", "full_name", "city", "country", "user", "is_default"]
    list_filter = ["country", "is_default"]
    search_fields = ["first_name", "last_name", "city", "postal_code", "user__email"]


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ["user", "product", "created_at"]
    search_fields = ["user__email", "product__name"]
