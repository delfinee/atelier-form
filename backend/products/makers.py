"""Public artisan discovery excludes internal demo and acceptance accounts."""
from django.conf import settings
from django.db.models import Q
from django.db.models.functions import Lower

from .models import Maker


def public_makers():
    internal = (
        Q(slug__in={'shared-school-demo', 'school-demo', settings.SELLER_SHARED_DEMO_SHOP})
        | Q(owner__email=settings.SELLER_SHARED_DEMO_EMAIL)
        | Q(name__iexact='School Demo')
        | Q(name__icontains='seller tester')
        | Q(discipline__icontains='seller tester')
        | Q(slug__icontains='seller-tester')
        | Q(slug__icontains='seller_tester')
        | Q(slug__startswith='acceptance-shop')
    )
    return Maker.objects.filter(is_active=True).exclude(internal).order_by(Lower('name'), 'pk')
