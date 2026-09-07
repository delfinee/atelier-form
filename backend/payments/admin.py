from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["order", "provider", "state", "amount", "currency", "created_at"]
    list_filter = ["provider", "state"]
    search_fields = ["order__order_number", "provider_session_id", "provider_payment_id"]
    # Provider identifiers are records of fact, not settings.
    readonly_fields = ["uuid", "provider_session_id", "provider_payment_id", "created_at", "updated_at"]
