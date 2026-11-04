"""Public catalogue boundary; never filters seller workspaces or order history.

Exact production identities verified through the public API on 2026-11-04.
Names alone are deliberately never a visibility criterion.
"""
from django.conf import settings
from django.db.models import Q


TEST_PRODUCTS = (
    ('52f7782d-7bc5-4e01-8666-442f66271f13', 'demo-sync-shared-catalogue-cup-86e9b80839', 'shared-school-demo'),
    ('a194e3c5-e843-45f5-8637-ad4b5f5f9705', 'mug-2', 'seller-c32d9f22cbea4c78'),
    ('81653267-3e98-40a0-b76a-11f905d8b537', 'mug', 'seller-c32d9f22cbea4c78'),
    ('676e119f-ff2c-4e51-92df-3de52c05d2b8', 'bh-test-1', 'chen-meilin'),
)
TEST_MAKER = ('24284c9f-1d4a-4d90-ab03-fb5eab3306d1', 'seller-c32d9f22cbea4c78')


def private_makers(prefix=''):
    return (Q(**{prefix + 'slug': settings.SELLER_SHARED_DEMO_SHOP})
            | Q(**{prefix + 'uuid': TEST_MAKER[0], prefix + 'slug': TEST_MAKER[1]}))


def public_makers(queryset):
    return queryset.filter(is_active=True).exclude(private_makers())


def public_products(queryset):
    hidden = Q()
    for uuid, slug, maker in TEST_PRODUCTS:
        hidden |= Q(uuid=uuid, slug=slug, maker__slug=maker)
    return (queryset.filter(is_active=True, maker__is_active=True)
            .exclude(private_makers('maker__')).exclude(hidden))
