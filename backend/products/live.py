"""Small revision markers for open storefront pages, without customer data."""
import hashlib
import json

from django.db.models import Count, Max, Sum
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from imagery.models import SiteImage
from orders.models import Order, SellerFulfillment
from .models import Maker, Product, ProductImage, ProductVariant


def _fingerprint(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _version(queryset, stock=False):
    fields = {'count': Count('pk'), 'updated': Max('updated_at')}
    if stock:
        fields['stock'] = Sum('stock_quantity')
    return queryset.aggregate(**fields)


@require_GET
def revisions(request):
    catalogue = _fingerprint(
        _version(Product.objects.filter(is_active=True), stock=True),
        _version(ProductVariant.objects.filter(product__is_active=True), stock=True),
        _version(ProductImage.objects.filter(product__is_active=True)),
        _version(Maker.objects.filter(is_active=True)),
        _version(SiteImage.objects.all()),
    )
    orders = ''
    if request.user.is_authenticated:
        orders = _fingerprint(_version(Order.objects.filter(user=request.user)),
            _version(SellerFulfillment.objects.filter(order__user=request.user)))
    response = JsonResponse({'catalogue': catalogue, 'orders': orders})
    response['Cache-Control'] = 'private, no-store'
    return response
