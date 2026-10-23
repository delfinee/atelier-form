"""No source download, development entry points or buyer checkout on this host."""
from django.urls import path
from seller_agent import release_views
from .seller_phone_urls import urlpatterns as phone_patterns, handler404, handler500

urlpatterns = [
    path('', release_views.home, name='seller_public_home'),
    path('privacy/', release_views.privacy, name='seller_privacy'),
    path('healthz/', release_views.health, name='seller_health'),
    path('account/login/', release_views.SellerLoginView.as_view(), name='login'),
] + [entry for entry in phone_patterns
     if str(entry.pattern) not in ('', 'seller/download/', 'account/login/')]
