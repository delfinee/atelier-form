"""Password-free school workspace over the existing storefront catalogue."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import JsonResponse
from products.models import Maker


class SharedSchoolDemoMiddleware:
    prefixes = ('/seller/ai/', '/seller/products/', '/api/seller/products/',
                '/api/seller-agent/v1/')
    blocked = ('/seller/ai/link/', '/api/seller-agent/v1/session/',
               '/api/seller-agent/v1/link/', '/api/seller-agent/v1/links/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        enabled = (getattr(settings, 'SELLER_SHARED_DEMO_ENABLED', False)
                   or request.get_host().partition(':')[0].lower().rstrip('.') in settings.SELLER_SHARED_DEMO_HOSTS)
        if not enabled or not request.path.startswith(self.prefixes):
            return self.get_response(request)
        if request.path.startswith(self.blocked):
            return JsonResponse({'detail': 'Account linking is not used in the shared school demo.'}, status=403)
        with transaction.atomic():
            user, _ = get_user_model().objects.get_or_create(
                email=settings.SELLER_SHARED_DEMO_EMAIL,
                defaults={'password': '!', 'is_seller': True, 'first_name': 'School', 'last_name': 'Demo'},
            )
            if not (user.is_active and user.is_seller) or user.is_staff or user.is_admin or user.is_superuser:
                return JsonResponse({'detail': 'The shared demo account configuration is invalid.'}, status=503)
            maker, _ = Maker.objects.get_or_create(
                slug=settings.SELLER_SHARED_DEMO_SHOP,
                defaults={'owner': user, 'name': 'School Demo', 'discipline': 'Handmade goods', 'location': 'Coursework'},
            )
            if maker.owner_id != user.pk or not maker.is_active:
                return JsonResponse({'detail': 'The shared demo shop configuration is invalid.'}, status=503)
        # Request-local identity only: never overwrite a visitor's real login.
        # SessionAuthentication still enforces CSRF for writes. Existing services
        # preserve existing catalogue records and their maker ownership.
        user._shared_catalogue = True
        request.user = user
        request.seller_shared_demo = True
        request.seller_public_demo = True
        response = self.get_response(request)
        response['Cache-Control'] = 'private, no-store'
        response['X-Robots-Tag'] = 'noindex, nofollow'
        return response
