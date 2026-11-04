from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils.translation import override

from accounts.permissions import IsSeller
from frontend import services
from frontend.catalogue_i18n import localize_product, localize_order_item_name
from frontend.catalogue_overrides import TOTE_COPY, TOTE_UUID
from orders.tests.factories import make_category, make_maker, make_product, make_seller_user, make_bare_order, make_order_item, make_cart, SHIPPING_ADDRESS
from products.models import Product, Maker
from products.publication import TEST_PRODUCTS, TEST_MAKER


@override_settings(SECURE_SSL_REDIRECT=False, SELLER_SHARED_DEMO_ENABLED=False, SELLER_SHARED_DEMO_HOSTS=[])
class CatalogueCleanupTests(TestCase):
    def setUp(self):
        self.category = make_category()
        self.owner = make_seller_user('cleanup@example.test')
        self.real = make_maker('chen-meilin', 'Chen Meilin')
        self.test_maker = Maker.objects.create(uuid=TEST_MAKER[0], slug=TEST_MAKER[1], name='seller tester', owner=self.owner)
        self.school = make_maker('shared-school-demo', 'School Demo')
        makers = {m.slug: m for m in (self.real, self.test_maker, self.school)}
        self.hidden = [Product.objects.create(uuid=u, slug=s, name=s, maker=makers[m], category=self.category, price=10, is_featured=True, is_new_arrival=True) for u,s,m in TEST_PRODUCTS]
        self.good = make_product(maker=self.real, category=self.category, slug='legitimate-mug', name='mug')

    def test_all_public_surfaces_exclude_exact_targets(self):
        for hidden in self.hidden:
            self.assertIsNone(services.get_product(hidden.slug))
            self.assertEqual(self.client.get('/api/products/' + hidden.slug + '/').status_code, 404)
            self.assertNotIn(hidden.slug, services.catalogue_payload())
        for items in (services.all_products(), services.featured_products(), services.new_arrivals(), services.related_products(self.good), services.products_by_maker('chen-meilin'), services.products_in_collection(self.category.slug), services.search('mug')['products']):
            self.assertFalse({p.pk for p in items} & {p.pk for p in self.hidden})
        self.assertIn(self.good.pk, [p.pk for p in services.all_products()])
        for maker in (self.school, self.test_maker):
            self.assertIsNone(services.get_maker(maker.slug))
            self.assertEqual(self.client.get('/api/makers/' + maker.slug + '/').status_code, 404)
        self.assertEqual(services.search('seller tester')['makers'], [])

    def test_future_shared_products_private_but_accessible_to_workspace(self):
        product = make_product(maker=self.school, category=self.category, slug='future-demo')
        self.assertFalse(Product.objects.active().filter(pk=product.pk).exists())
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())
        self.school.refresh_from_db()
        self.assertTrue(self.school.is_active)

    def test_hidden_product_in_old_cart_cannot_checkout(self):
        from orders.services import create_order
        from config.exceptions import InsufficientStock
        cart = make_cart(self.owner, (self.hidden[1], 1))
        with self.assertRaises(InsufficientStock):
            create_order(cart=cart, email='buyer@example.test', shipping_address=SHIPPING_ADDRESS)
        self.assertTrue(cart.items.exists())

    def test_recommendations_and_cached_assistant_cards_hide_targets(self):
        from recommendations.services import popular_products, similar_products
        from concierge.display import localize_result
        for ranked in (popular_products(100), similar_products(self.good, 100)):
            self.assertFalse({r.product.pk for r in ranked} & {p.pk for p in self.hidden})
        result = localize_result({'products': [{'slug': p.slug} for p in self.hidden]}, 'en')
        self.assertEqual(result['products'], [])

    def test_cleanup_refuses_identity_drift(self):
        self.hidden[0].slug = 'changed-by-seller'
        self.hidden[0].save()
        with self.assertRaises(CommandError):
            call_command('cleanup_test_catalogue', stdout=StringIO())

    def test_cleanup_dry_run_apply_repeat_and_history(self):
        line = make_order_item(order=make_bare_order(), product=self.hidden[1])
        call_command('cleanup_test_catalogue', stdout=StringIO())
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_seller)
        with TemporaryDirectory() as directory:
            with self.assertRaises(CommandError):
                call_command('cleanup_test_catalogue', apply=True, backup=str(Path(directory)/'wrong.json'), confirmed_owner_id=-1, stdout=StringIO())
            for i in range(2):
                call_command('cleanup_test_catalogue', apply=True, backup=str(Path(directory)/f'{i}.json'), confirmed_owner_id=self.owner.pk, stdout=StringIO())
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_seller)
        self.assertTrue(self.owner.is_active)
        self.assertFalse(IsSeller().has_permission(SimpleNamespace(user=self.owner), None))
        line.refresh_from_db()
        self.assertEqual(line.product_id, self.hidden[1].pk)
        self.real.refresh_from_db()
        self.school.refresh_from_db()
        self.assertTrue(self.real.is_active and self.school.is_active)

    def test_tote_translation_is_exact_and_does_not_write(self):
        tote = Product.objects.create(uuid=TOTE_UUID, slug='curtain-tote-bag', maker=self.real, category=self.category, price=48, **TOTE_COPY)
        with override('zh-hans'):
            display = localize_product(tote)
            self.assertEqual(display.name, '窗帘布托特包')
            self.assertIn('窗帘布料', display.description)
            self.assertEqual(services.get_product(tote.slug).name, '窗帘布托特包')
            response = self.client.get('/api/products/curtain-tote-bag/', HTTP_ACCEPT_LANGUAGE='zh-hans')
            self.assertEqual(response.json()['name'], '窗帘布托特包')
            line = make_order_item(order=make_bare_order(), product=tote)
            self.assertEqual(localize_order_item_name(line), '窗帘布托特包')
            self.assertEqual(line.product_name, 'Curtain Tote Bag')
            tote.description = 'Seller edited description'
            self.assertEqual(localize_product(tote).description, tote.description)
            tote.uuid = self.good.uuid
            self.assertEqual(localize_product(tote).name, 'Curtain Tote Bag')
        tote.refresh_from_db()
        with override('en'):
            self.assertEqual(localize_product(tote).name, 'Curtain Tote Bag')
        self.assertEqual(tote.description, TOTE_COPY['description'])
