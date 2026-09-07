from django.contrib import admin

from .models import Category, Collection, Maker, Product, ProductImage, ProductVariant


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ["group", "label", "sku", "swatch", "price_override", "stock_quantity", "is_active"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "maker", "price", "stock_status",
                    "stock_quantity", "is_active", "is_featured"]
    list_filter = ["is_active", "is_featured", "is_new_arrival", "stock_status", "category", "maker"]
    search_fields = ["name", "slug", "short_description", "description"]
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ["collections"]
    inlines = [ProductImageInline, ProductVariantInline]
    readonly_fields = ["uuid", "stock_status", "created_at", "updated_at"]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.refresh_stock_status()


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "sort_order", "is_active"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_featured", "is_active", "sort_order"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Maker)
class MakerAdmin(admin.ModelAdmin):
    list_display = ["name", "discipline", "location", "since", "is_featured", "is_active"]
    search_fields = ["name", "discipline", "location"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ["sku", "product", "group", "label", "stock_quantity", "is_active"]
    list_filter = ["group", "is_active"]
    search_fields = ["sku", "label", "product__name"]
