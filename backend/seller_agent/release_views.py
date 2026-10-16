"""Public release information and restricted website login."""
import hashlib
from django.conf import settings
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


def public_context():
    return {'operator': getattr(settings, 'SELLER_OPERATOR', ''),
            'contact': getattr(settings, 'SELLER_CONTACT_EMAIL', '')}


@require_GET
def home(request):
    return render(request, 'seller_agent/public_home.html', public_context())


@require_GET
def privacy(request):
    return render(request, 'seller_agent/privacy.html', public_context())


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        return JsonResponse({'ok': False}, status=503)
    return JsonResponse({'ok': True})


class SellerLoginView(LoginView):
    template_name = 'seller_agent/phone_login.html'
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        # Caddy overwrites X-Forwarded-For; this service has no public HTTP port.
        address = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '')).split(',')[-1].strip()
        key = 'seller-login:' + hashlib.sha256(address.encode()).hexdigest()
        attempts = cache.get(key, 0)
        if attempts >= 20:
            response = HttpResponse('Too many sign-in attempts. Please wait five minutes.', status=429)
            response['Retry-After'] = '300'
            return response
        cache.set(key, attempts + 1, timeout=300)
        return super().post(request, *args, **kwargs)


class PrivateResponses:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(('/seller/', '/account/', '/api/')):
            response['Cache-Control'] = 'private, no-store'
            response['X-Robots-Tag'] = 'noindex, nofollow'
        return response
