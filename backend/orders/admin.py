from django.contrib import admin

from .models import Cart, CartItem, Order, OrderItem, OrderNumberSequence, ReturnRequest, SellerFulfillment


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    # Snapshots are historical records: readable, never editable.
    readonly_fields = ["product", "variant", "maker", "maker_name", "sku", "product_slug",
                       "product_name", "variant_name", "image", "unit_price", "quantity",
                       "line_total"]
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["order_number", "customer_email", "status", "payment_status",
                    "fulfillment_status", "total", "placed_at"]
    list_filter = ["status", "payment_status", "fulfillment_status", "delivery_method"]
    search_fields = ["order_number", "customer_email", "tracking_number"]
    readonly_fields = ["uuid", "order_number", "subtotal", "total", "shipping_address_snapshot",
                       "billing_address_snapshot", "placed_at", "created_at", "updated_at"]
    inlines = [OrderItemInline]
    date_hierarchy = "placed_at"


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["uuid", "user", "session_key", "is_active", "updated_at"]
    list_filter = ["is_active"]
    inlines = [CartItemInline]


admin.site.register(OrderNumberSequence)


@admin.register(SellerFulfillment)
class SellerFulfillmentAdmin(admin.ModelAdmin):
    list_display = ["order", "maker", "status", "carrier", "tracking_number", "shipped_at"]
    list_filter = ["status"]
    search_fields = ["order__order_number", "maker__name", "tracking_number"]
    readonly_fields = ["uuid", "created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ["order", "maker", "order_item", "quantity", "reason", "status",
                    "refund_amount", "created_at"]
    list_filter = ["status", "reason"]
    search_fields = ["order__order_number", "maker__name", "order_item__product_name"]
    readonly_fields = ["uuid", "order", "order_item", "maker", "buyer", "created_at", "updated_at"]
    date_hierarchy = "created_at"
