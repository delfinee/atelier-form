"""Each visitor gets a synthetic shop; no password or real account is accepted."""
import hashlib
from uuid import uuid4
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.core.cache import cache
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from products.models import Category, Maker, Product
from orders.models import Order, OrderItem, SellerFulfillment, OrderStatus, PaymentStatus

SUFFIX = '@public-demo.invalid'


def enabled():
    if not getattr(settings, 'SELLER_PUBLIC_DEMO', False):
        raise Http404


@require_GET
@ensure_csrf_cookie
def home(request):
    enabled()
    return render(request, 'seller_agent/demo_home.html', {
        'seller_ai_enabled': bool(settings.SELLER_AGENT_USE_LLM and settings.SELLER_AGENT_API_KEY),
    })


@require_POST
def start(request):
    enabled()
    if request.user.is_authenticated:
        return redirect('seller_ai')
    address = request.META.get('HTTP_CF_CONNECTING_IP', request.META.get('REMOTE_ADDR', ''))
    key = 'demo-start:' + hashlib.sha256(address.encode()).hexdigest()
    cache.add(key, 0, 3600)
    try:
        attempts = cache.incr(key)
    except ValueError:
        attempts = 1
        cache.set(key, attempts, 3600)
    if attempts > 30 or get_user_model().objects.filter(email__endswith=SUFFIX).count() >= 1000:
        return HttpResponse('The demo is busy. Please try again later.', status=429)
    with transaction.atomic():
        suffix = uuid4().hex
        user = get_user_model().objects.create_user(email='visitor-' + suffix + SUFFIX,
                                                   password=None, is_seller=True)
        maker = Maker.objects.create(owner=user, name='Your demo studio', slug='demo-' + suffix)
        category, _ = Category.objects.get_or_create(slug='ceramics', defaults={'name': 'Ceramics'})
        for index, (name, price, stock) in enumerate([('Ocean Blue Mug', '20.00', 7),
                ('Handmade Tea Bowl', '32.00', 3), ('Ceramic Flower Vase', '45.00', 12)]):
            product = Product.objects.create(maker=maker, category=category, name=name,
                slug=f'demo-{suffix}-{index}', description='Synthetic product for testing the seller workspace.',
                price=price, stock_quantity=stock, is_active=True, currency='SGD')
            if index == 0:
                order = Order.objects.create(order_number='DEMO-' + suffix[:16],
                    status=OrderStatus.CONFIRMED, payment_status=PaymentStatus.PAID,
                    customer_email='sample-buyer@example.invalid', currency='SGD',
                    shipping_address_snapshot={'first_name': 'Sample', 'last_name': 'Buyer',
                        'address_line_1': 'DEMO ONLY - DO NOT SHIP', 'city': 'Sample City', 'country': 'SG'})
                OrderItem.objects.create(order=order, product=product, maker=maker,
                    product_slug=product.slug, product_name=product.name, maker_name=maker.name,
                    unit_price=product.price, quantity=1, line_total=product.price)
                SellerFulfillment.objects.create(order=order, maker=maker)
                order.recalculate()
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session.set_expiry(86400)
    return redirect('seller_ai')


class DemoGuard:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.seller_public_demo = True
        if request.user.is_authenticated and not request.user.email.endswith(SUFFIX):
            return HttpResponseForbidden('Only disposable demo accounts can use this service.')
        # No native identity exchange/linking or private account endpoints on this deployment.
        if request.path.startswith(('/api/seller-agent/v1/session/', '/api/seller-agent/v1/link/',
                                    '/api/seller-agent/v1/links/')) and request.method != 'GET':
            return HttpResponseForbidden('WeChat account linking is unavailable in the public website demo.')
        response = self.get_response(request)
        response['Cache-Control'] = 'private, no-store'
        response['X-Robots-Tag'] = 'noindex, nofollow'
        return response
