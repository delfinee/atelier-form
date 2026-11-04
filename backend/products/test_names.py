from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils.translation import override

from concierge.shopping import discover
from frontend.catalogue_i18n import localize_product
from orders.tests.factories import make_category, make_maker, make_product
from .models import Product, ProductNameTranslation
from .names import localized_product_name, warm_product_names


@override_settings(
    ALLOWED_HOSTS=['testserver', 'school.test'], SELLER_SHARED_DEMO_HOSTS=['school.test'],
    SELLER_AGENT_ENABLED=True, SELLER_AGENT_USE_LLM=False, BUYER_AI_USE_LLM=False,
    SECURE_SSL_REDIRECT=False,
    STORAGES={**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
)
class ProductNameSyncTests(TestCase):
    def setUp(self):
        cache.clear()
        self.maker = make_maker('names-maker', 'Studio')
        self.category = make_category('ceramics', 'Ceramics')
        self.product = make_product(maker=self.maker, category=self.category,
            name='云白手作陶瓷杯', slug='cloud-cup', price='39.00', stock_quantity=20)

    @patch('concierge.display._translate')
    def test_chinese_product_has_one_english_name_on_every_surface(self, translate):
        translate.return_value = {'云白手作陶瓷杯': 'Cloud White Handmade Ceramic Cup'}
        expected = 'Cloud White Handmade Ceramic Cup'
        response = self.client.get('/api/products/cloud-cup/', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['name'], expected)
        self.assertEqual(response.json()['original_name'], '云白手作陶瓷杯')
        cache.clear()
        translate.reset_mock()
        self.assertContains(self.client.get('/products/cloud-cup/', HTTP_ACCEPT_LANGUAGE='en'), expected)
        snapshot = self.client.get('/api/seller-agent/v1/snapshot/', HTTP_HOST='school.test', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(snapshot.json()['products'][0]['name'], expected)
        self.assertEqual(snapshot.json()['products'][0]['canonical_name'], '云白手作陶瓷杯')
        with override('en'):
            self.assertEqual(discover('Compare prices', action='price', language='en')['products'][0]['name'], expected)
        translate.assert_not_called()
        self.assertContains(self.client.get('/products/cloud-cup/', HTTP_ACCEPT_LANGUAGE='zh-hans'), '云白手作陶瓷杯')
        self.product.refresh_from_db()
        self.assertEqual((self.product.slug, self.product.name, self.product.stock_quantity),
                         ('cloud-cup', '云白手作陶瓷杯', 20))

    @patch('concierge.display._translate')
    def test_english_product_gets_same_chinese_name_in_store_and_seller(self, translate):
        self.product.name = 'Ocean Blue Cup'
        self.product.save()
        translate.return_value = {'Ocean Blue Cup': '海蓝陶瓷杯'}
        public = self.client.get('/api/products/cloud-cup/', HTTP_ACCEPT_LANGUAGE='zh-hans').json()
        seller = self.client.get('/api/seller-agent/v1/snapshot/', HTTP_HOST='school.test',
                                 HTTP_ACCEPT_LANGUAGE='zh-hans').json()
        self.assertEqual(public['name'], '海蓝陶瓷杯')
        self.assertEqual(seller['products'][0]['name'], public['name'])
        self.assertContains(self.client.get('/shop/', HTTP_ACCEPT_LANGUAGE='zh-hans'), public['name'])
        self.assertEqual(translate.call_count, 1)

    @patch('concierge.display._translate')
    def test_rename_invalidates_old_translation_without_changing_product_identity(self, translate):
        translate.return_value = {'云白手作陶瓷杯': 'Cloud White Cup'}
        self.assertEqual(localized_product_name(self.product, 'en'), 'Cloud White Cup')
        Product.objects.filter(pk=self.product.pk).update(name='山茶手作陶瓷杯')
        translate.return_value = {'山茶手作陶瓷杯': 'Camellia Handmade Cup'}
        self.product.refresh_from_db()
        self.assertEqual(localized_product_name(self.product, 'en'), 'Camellia Handmade Cup')
        row = ProductNameTranslation.objects.get(product=self.product)
        self.assertEqual((row.source_name, row.english, row.chinese),
                         ('山茶手作陶瓷杯', 'Camellia Handmade Cup', '山茶手作陶瓷杯'))
        self.assertEqual(self.product.slug, 'cloud-cup')

    @patch('concierge.display._translate')
    def test_batch_translation_and_search_for_translated_name(self, translate):
        other = make_product(maker=self.maker, category=self.category, name='山茶杯', slug='camellia-cup')
        translate.return_value = {'云白手作陶瓷杯': 'Cloud White Cup', '山茶杯': 'Camellia Cup'}
        warm_product_names([self.product, other], 'en')
        translate.assert_called_once()
        self.assertEqual(list(Product.objects.search('Cloud White').values_list('slug', flat=True)), ['cloud-cup'])
        self.assertEqual(list(Product.objects.search('山茶').values_list('slug', flat=True)), ['camellia-cup'])

    @patch('concierge.display._translate')
    def test_concurrent_rename_does_not_save_translation_for_wrong_source(self, translate):
        def renamed_during_translation(*args):
            Product.objects.filter(pk=self.product.pk).update(name='新名称')
            return {'云白手作陶瓷杯': 'Cloud White Cup'}
        translate.side_effect = renamed_during_translation
        localized_product_name(self.product, 'en')
        self.assertFalse(ProductNameTranslation.objects.filter(product=self.product).exists())

    @patch('concierge.display._translate')
    def test_unavailable_translation_keeps_original_without_saving_bad_data(self, translate):
        translate.return_value = {}
        self.assertEqual(localized_product_name(self.product, 'en'), self.product.name)
        self.assertFalse(ProductNameTranslation.objects.filter(product=self.product).exists())

    def test_unsaved_draft_does_not_call_database_or_provider(self):
        draft = Product(name='尚未保存的杯子', slug='draft')
        with self.assertNumQueries(0), patch('concierge.display._translate') as translate, override('en'):
            self.assertEqual(localize_product(draft).name, draft.name)
            translate.assert_not_called()

    @patch('concierge.display._translate')
    def test_translating_second_language_retains_the_first_translation(self, translate):
        self.product.name = 'Blue Sky 云白杯'
        self.product.save()
        translate.return_value = {'Blue Sky 云白杯': '蓝天云白杯'}
        self.assertEqual(localized_product_name(self.product, 'zh-hans'), '蓝天云白杯')
        translate.return_value = {'Blue Sky 云白杯': 'Blue Sky Cloud White Cup'}
        self.assertEqual(localized_product_name(self.product, 'en'), 'Blue Sky Cloud White Cup')
        row = ProductNameTranslation.objects.get(product=self.product)
        self.assertEqual((row.english, row.chinese), ('Blue Sky Cloud White Cup', '蓝天云白杯'))
