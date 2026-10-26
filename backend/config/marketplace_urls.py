"""Buyer storefront and authenticated seller web/desktop/Mini Program channels."""
from django.urls import path
from concierge import buyer_views
from seller_agent import views as seller_views, release_views
from .urls import urlpatterns as all_patterns

# Retain the team's authenticated seller dashboard, product editor, orders and
# human messaging. Web, desktop and WeChat use the same scoped business services.
# Only the legacy isolated demos and browser Mini Program simulator stay hidden.
urlpatterns = [entry for entry in all_patterns if not str(entry.pattern).startswith(
    ('admin/', 'seller/assistant/', 'seller/workbench/', 'seller/ai/',
     'seller/mini-program/', 'customer/preview/', 'api/mini-store/'))]
urlpatterns += [
    path('healthz/', release_views.health, name='marketplace_health'),
    path('seller/mini-program/', buyer_views.seller_mini_program, name='seller_mini_program'),
    path('seller/ai/', seller_views.desk, name='seller_ai'),
    path('seller/ai/link/', seller_views.link),
]
