from datetime import timedelta

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from frontend import services
from orders.tests.factories import make_category, make_maker
from .models import Product


@override_settings(
    ALLOWED_HOSTS=['testserver', 'school.test'], SELLER_SHARED_DEMO_HOSTS=['school.test'],
    SECURE_SSL_REDIRECT=False, LANGUAGE_CODE='en',
    STORAGES={**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
)
class NewArrivalPublicationTests(TestCase):
    def setUp(self):
        self.maker = make_maker('arrival-maker', 'Arrival Studio')
        self.category = make_category('ceramics', 'Ceramics')
        self.older = Product.objects.create(name='Older Cup', slug='older-cup', maker=self.maker,
            category=self.category, price='20', is_new_arrival=True, sort_weight=999)
        self.draft = Product.objects.create(name='New Team Cup', slug='new-team-cup', maker=self.maker,
            category=self.category, price='39', is_active=False, is_new_arrival=False)
        Product.objects.filter(pk=self.older.pk).update(published_at=timezone.now() - timedelta(days=2))
        Product.objects.filter(pk=self.draft.pk).update(created_at=timezone.now() - timedelta(days=10))
        self.older.refresh_from_db()
        self.draft.refresh_from_db()

    def publish(self):
        response = self.client.patch('/api/seller/products/new-team-cup/', {'is_active': True},
            content_type='application/json', HTTP_HOST='school.test', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(response.status_code, 200, response.content)
        self.draft.refresh_from_db()

    def test_saved_draft_is_hidden_until_published(self):
        self.assertIsNone(self.draft.published_at)
        self.assertEqual([p.slug for p in services.new_arrivals()], ['older-cup'])
        self.publish()
        self.assertIsNotNone(self.draft.published_at)
        self.assertFalse(self.draft.is_new_arrival)
        self.assertEqual([p.slug for p in services.new_arrivals()], ['new-team-cup', 'older-cup'])

    def test_home_shop_and_public_api_use_publication_time(self):
        self.publish()
        home = self.client.get('/', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(home.status_code, 200)
        self.assertEqual(home.context['new_arrivals'][0].slug, self.draft.slug)
        self.assertContains(home, '/products/new-team-cup/')
        self.assertEqual(services.filter_products(sort='newest')[0].slug, self.draft.slug)
        self.assertEqual(services.sort_products([self.older, self.draft], 'newest')[0].slug, self.draft.slug)
        response = self.client.get('/api/products/?sort=newest', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        rows = result['items'] if isinstance(result, dict) else result
        self.assertEqual(rows[0]['slug'], self.draft.slug)

    def test_price_and_stock_changes_do_not_make_product_new_again(self):
        published = self.older.published_at
        self.older.price = '21'
        self.older.stock_quantity = 15
        self.older.save(update_fields=['price', 'stock_quantity', 'updated_at'])
        self.older.refresh_from_db()
        self.assertEqual(self.older.published_at, published)
        self.older.save()
        self.older.refresh_from_db()
        self.assertEqual(self.older.published_at, published)

    def test_republishing_has_a_new_publication_time(self):
        self.older.is_active = False
        self.older.save(update_fields=['is_active'])
        prior = self.older.published_at
        self.older.is_active = True
        self.older.save(update_fields=['is_active'])
        self.older.refresh_from_db()
        self.assertGreater(self.older.published_at, prior)

    def test_publication_changes_live_revision(self):
        before = self.client.get('/api/store-revisions/').json()['catalogue']
        self.publish()
        after = self.client.get('/api/store-revisions/').json()['catalogue']
        self.assertNotEqual(before, after)
