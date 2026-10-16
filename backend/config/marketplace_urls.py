"""Buyer storefront plus seller Mini Program API and secure web handoffs."""
from django.urls import path
from django.views.generic import RedirectView
from concierge import buyer_views
from seller_agent import views as seller_views, release_views
from .urls import urlpatterns as all_patterns

# Keep the existing buyer catalogue/account/cart/checkout routes. Seller chat and
# the old demo console are not a second public workspace in this delivery.
urlpatterns = [entry for entry in all_patterns if not str(entry.pattern).startswith(
    ('admin/', 'seller/', 'customer/preview/', 'api/mini-store/'))]
urlpatterns += [
    path('healthz/', release_views.health, name='marketplace_health'),
    path('seller/mini-program/', buyer_views.seller_mini_program, name='seller_mini_program'),
    path('seller/', RedirectView.as_view(url='/seller/mini-program/'), name='seller_dashboard'),
    path('seller/ai/', RedirectView.as_view(url='/seller/mini-program/'), name='seller_ai'),
    path('seller/ai/link/', seller_views.link),
]
# Product editors are authenticated handoffs from WeChat; preserve their URLs.
urlpatterns += [entry for entry in all_patterns if str(entry.pattern).startswith('seller/products/')]
# Keep named destinations used by old account templates while routing everyday
# seller work to the Mini Program instead of exposing another dashboard.
urlpatterns += [path(str(entry.pattern), RedirectView.as_view(url='/seller/mini-program/'), name=entry.name)
    for entry in all_patterns if str(entry.pattern).startswith(('seller/orders/', 'seller/messages/')) and getattr(entry, 'name', None)]
