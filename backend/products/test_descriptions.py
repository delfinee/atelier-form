from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils.translation import override

from concierge.shopping import discover
from frontend.catalogue_i18n import localize_product
from orders.tests.factories import make_category, make_maker
from .descriptions import localized_product_descriptions
from .models import Product, ProductNameTranslation, ProductTextTranslation

ZH = '白色陶瓷杯，容量300毫升。\n适合饮茶或喝咖啡。'
EN = 'A white ceramic cup with a 300 ml capacity.\nSuitable for tea or coffee.'
SHORT_ZH = '日常使用的白色陶瓷杯。'
SHORT_EN = 'A white ceramic cup for everyday use.'


@override_settings(
    ALLOWED_HOSTS=['testserver', 'school.test'], SELLER_SHARED_DEMO_HOSTS=['school.test'],
    SELLER_AGENT_ENABLED=True, SELLER_AGENT_USE_LLM=False, BUYER_AI_USE_LLM=False,
    SECURE_SSL_REDIRECT=False,
    STORAGES={**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
)
class ProductDescriptionSyncTests(TestCase):
    def setUp(self):
        cache.clear()
        self.product = Product.objects.create(maker=make_maker('description-maker', 'Studio'),
            category=make_category('ceramics', 'Ceramics'), name='Demo Cup', slug='description-cup',
            description=ZH, short_description=SHORT_ZH, price='39.00', stock_quantity=20)
        ProductNameTranslation.objects.create(product=self.product, source_name='Demo Cup',
                                              english='Demo Cup', chinese='演示杯')

    @patch('concierge.display._translate')
    def test_full_and_short_descriptions_match_on_store_seller_and_chat(self, translate):
        translate.return_value = {ZH: EN, SHORT_ZH: SHORT_EN}
        public = self.client.get('/api/products/description-cup/', HTTP_ACCEPT_LANGUAGE='en').json()
        self.assertEqual(public['description'], EN)
        self.assertEqual(public['short_description'], SHORT_EN)
        self.assertEqual(public['original_description'], ZH)
        self.assertEqual(translate.call_count, 1)
        cache.clear()
        translate.reset_mock()
        self.assertContains(self.client.get('/products/description-cup/', HTTP_ACCEPT_LANGUAGE='en'),
                            'A white ceramic cup with a 300 ml capacity.')
        seller = self.client.get('/api/seller-agent/v1/snapshot/', HTTP_HOST='school.test',
                                 HTTP_ACCEPT_LANGUAGE='en').json()['products'][0]
        self.assertEqual(seller['description'], EN)
        self.assertEqual(seller['short_description'], SHORT_EN)
        with override('en'):
            chat = discover('Compare prices', action='price', language='en')['products'][0]
        self.assertEqual(chat['description'], EN)
        translate.assert_not_called()
        self.product.refresh_from_db()
        self.assertEqual((self.product.description, self.product.short_description), (ZH, SHORT_ZH))
        self.assertEqual((self.product.price, self.product.stock_quantity), (39, 20))

    @patch('concierge.display._translate')
    def test_english_description_is_translated_for_chinese_pages(self, translate):
        self.product.description, self.product.short_description = EN, SHORT_EN
        self.product.save()
        translate.return_value = {EN: ZH, SHORT_EN: SHORT_ZH}
        public = self.client.get('/api/products/description-cup/', HTTP_ACCEPT_LANGUAGE='zh-hans').json()
        self.assertEqual((public['description'], public['short_description']), (ZH, SHORT_ZH))
        self.assertContains(self.client.get('/products/description-cup/', HTTP_ACCEPT_LANGUAGE='zh-hans'),
                            '白色陶瓷杯，容量300毫升。')
        self.assertEqual(translate.call_count, 1)

    @patch('concierge.display._translate')
    def test_editing_description_invalidates_only_its_translation(self, translate):
        translate.return_value = {ZH: EN, SHORT_ZH: SHORT_EN}
        localized_product_descriptions(self.product, 'en')
        changed = '白色陶瓷杯，容量350毫升。'
        Product.objects.filter(pk=self.product.pk).update(description=changed)
        self.product.refresh_from_db()
        translate.return_value = {changed: 'A white ceramic cup with a 350 ml capacity.'}
        output = localized_product_descriptions(self.product, 'en')
        self.assertEqual(output['description'], 'A white ceramic cup with a 350 ml capacity.')
        self.assertEqual(output['short_description'], SHORT_EN)
        self.assertEqual(ProductTextTranslation.objects.get(product=self.product, field='description').source_text, changed)

    @patch('concierge.display._translate')
    def test_concurrent_edit_cannot_save_a_translation_of_the_old_description(self, translate):
        self.product.short_description = ''
        self.product.save()
        def edit(*args, **kwargs):
            Product.objects.filter(pk=self.product.pk).update(description='新描述')
            return {ZH: EN}
        translate.side_effect = edit
        localized_product_descriptions(self.product, 'en')
        self.assertFalse(ProductTextTranslation.objects.filter(product=self.product).exists())

    def test_empty_and_unsaved_descriptions_need_no_queries(self):
        draft = Product(name='Draft', slug='draft', description='', short_description='')
        with self.assertNumQueries(0), patch('concierge.display._translate') as translate:
            self.assertEqual(localized_product_descriptions(draft, 'en'),
                             {'description': '', 'short_description': ''})
            translate.assert_not_called()

    @patch('concierge.display._translate')
    def test_failure_preserves_original_description(self, translate):
        translate.return_value = {}
        self.assertEqual(localized_product_descriptions(self.product, 'en')['description'], ZH)
        self.assertFalse(ProductTextTranslation.objects.filter(product=self.product).exists())

    @patch('concierge.display._translate')
    def test_localizing_never_mutates_the_input_product(self, translate):
        translate.return_value = {ZH: EN, SHORT_ZH: SHORT_EN}
        before = dict(self.product.__dict__)
        with override('en'):
            displayed = localize_product(self.product)
        self.assertEqual(displayed.description, EN)
        self.assertEqual(self.product.__dict__, before)
