"""Acceptance for the integrated buyer surface and the preserved seller API."""
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch, Mock
import json
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from products.models import Category, Maker, Product, ProductVariant
from reviews.models import Review
from orders.models import Order
from .shopping import discover


@override_settings(BUYER_AI_USE_LLM=False, SECURE_SSL_REDIRECT=False,
    STORAGES={**settings.STORAGES, 'staticfiles': {'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class BuyerDiscoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name='Ceramics', slug='ceramics')
        cls.maker = Maker.objects.create(name='Studio', slug='studio')
        cls.user = get_user_model().objects.create_user(email='reviewer@example.test')
        cls.blue = Product.objects.create(name='Blue ceramic mug', slug='blue-mug', category=cls.category,
            maker=cls.maker, price='30', stock_quantity=5, materials=['Stoneware'])
        cls.white = Product.objects.create(name='White ceramic cup', slug='white-cup', category=cls.category,
            maker=cls.maker, price='15', stock_quantity=5)
        cls.unreviewed = Product.objects.create(name='Blue ceramic cup', slug='unreviewed', category=cls.category,
            maker=cls.maker, price='10', stock_quantity=1)
        cls.inactive = Product.objects.create(name='Blue ceramic mug secret', slug='hidden', category=cls.category,
            maker=cls.maker, price='1', stock_quantity=5, is_active=False)
        Review.objects.create(product=cls.blue, user=cls.user, rating=5, is_published=True)
        Review.objects.create(product=cls.white, user=cls.user, rating=1, is_published=False)

    def setUp(self):
        cache.clear()

    def test_real_products_cheapest_and_live_review_facts(self):
        r = discover('Find the cheapest ceramic cups')
        self.assertEqual([p['slug'] for p in r['products']], ['unreviewed','white-cup','blue-mug'])
        self.assertIsNone(r['products'][1]['rating'])
        self.assertEqual(r['products'][2]['rating'], 5)
        for p in r['products']:
            self.assertEqual(p['url'], '/products/' + p['slug'] + '/')
        self.assertEqual(discover('Find ceramic mugs with good reviews')['products'][0]['slug'], 'blue-mug')

    def test_multiturn_colour_budget_review_and_stale_price(self):
        a = discover('Find ceramic mugs')
        b = discover('Only blue ones under CNY 35', a['context'])
        c = discover('With good reviews', b['context'])
        self.assertEqual([p['slug'] for p in c['products']], ['blue-mug'])
        Product.objects.filter(pk=self.blue.pk).update(price='50')
        self.assertFalse(discover('Compare these', c['context'])['products'])

    def test_chinese_refinement_and_no_result(self):
        a = discover('找陶瓷杯')
        b = discover('只要蓝色，预算20元', a['context'])
        self.assertEqual([p['slug'] for p in b['products']], ['unreviewed'])
        self.assertFalse(discover('只要好评', b['context'])['products'])
        self.assertFalse(discover('find purple flying teapots')['products'])

    def test_matching_variant_sets_price_and_stock(self):
        p = Product.objects.create(name='Ceramic mug options', slug='options', category=self.category,
            maker=self.maker, price='1', stock_quantity=999)
        ProductVariant.objects.create(product=p,label='Blue',sku='BLUE-1',price_override='40',stock_quantity=2)
        ProductVariant.objects.create(product=p,label='White',sku='WHITE-1',price_override='2',stock_quantity=20)
        r = discover('Blue ceramic mugs under CNY 35')
        self.assertNotIn('options', [x['slug'] for x in r['products']])
        r = discover('Blue ceramic mugs under CNY 45')
        actual = next(x for x in r['products'] if x['slug'] == 'options')
        self.assertEqual(actual['price'], '40.00')
        self.assertEqual(actual['quantity'], 2)

    def test_made_to_order_never_shows_synthetic_million_stock(self):
        Product.objects.filter(pk=self.blue.pk).update(is_made_to_order=True)
        p = next(p for p in discover('Find ceramic mugs')['products'] if p['slug'] == 'blue-mug')
        self.assertIsNone(p['quantity'])

    def test_discovery_never_executes_store_commands(self):
        r = discover('set stock blue-mug to 0')
        self.blue.refresh_from_db()
        self.assertEqual(self.blue.stock_quantity, 5)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(r['products'])

    def test_new_search_clears_old_colour_and_pagination_does_not_repeat(self):
        a = discover('Find ceramic mugs')
        b = discover('Only blue', a['context'])
        c = discover('Find ceramic mugs', b['context'])
        self.assertIn('white-cup', [p['slug'] for p in c['products']])
        for i in range(5):
            Product.objects.create(name=f'Extra ceramic mug {i}',slug=f'extra-{i}',category=self.category,
                maker=self.maker,price='20',stock_quantity=5)
        a = discover('Find ceramic mugs')
        b = discover('show two more', a['context'])
        self.assertEqual(len(b['products']),2)
        self.assertFalse(set(p['slug'] for p in a['products']) & set(p['slug'] for p in b['products']))

    def test_seller_change_is_immediately_visible_to_buyer(self):
        from seller_agent.models import Conversation
        from seller_agent.services import prepare_change, confirm_change
        seller = get_user_model().objects.create_user(email='owner@example.test',is_seller=True)
        self.maker.owner = seller
        self.maker.save(update_fields=['owner'])
        conversation = Conversation.objects.create(user=seller)
        change = prepare_change(seller,conversation.uuid,uuid4(),'price','blue-mug',{'price':'31.50'})
        self.assertEqual(next(p for p in discover('ceramic mugs')['products'] if p['slug']=='blue-mug')['price'],'30.00')
        confirm_change(seller,change.uuid,'wechat')
        self.assertEqual(next(p for p in discover('ceramic mugs')['products'] if p['slug']=='blue-mug')['price'],'31.50')

    def test_currency_groups_do_not_claim_an_exchange_conversion(self):
        Product.objects.create(name='Ceramic mug dollars',slug='usd-mug',category=self.category,
            maker=self.maker,price='2',currency='USD',stock_quantity=5)
        r = discover('Find cheapest ceramic mugs')
        self.assertIn('Currencies are grouped separately',r['comparison_basis'])
        r = discover('Find ceramic mugs under CNY 20')
        self.assertTrue(all(p['currency']=='CNY' for p in r['products']))

    @override_settings(ROOT_URLCONF='config.marketplace_urls')
    def test_existing_seller_account_keeps_secure_edit_handoff(self):
        self.user.is_seller = True
        self.user.save(update_fields=['is_seller'])
        self.maker.owner = self.user
        self.maker.save(update_fields=['owner'])
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/account/').status_code,200)
        self.assertEqual(self.client.get('/seller/products/blue-mug/edit/').status_code,200)

    @override_settings(ROOT_URLCONF='config.marketplace_urls')
    def test_home_contains_buyer_assistant_and_seller_is_mobile_entry(self):
        r = self.client.get('/')
        self.assertContains(r, 'buyer-panel')
        self.assertContains(r, 'data-buyer-start')
        self.assertEqual(self.client.get('/seller/ai/').url, '/seller/mini-program/')
        self.assertEqual(self.client.get('/admin/').status_code, 404)
        self.assertEqual(self.client.get('/seller/workbench/').status_code, 404)
        self.assertContains(self.client.get('/seller/mini-program/'), 'WeChat')

    def test_session_isolation_retry_and_csrf(self):
        client = Client(enforce_csrf_checks=True)
        data = {'text':'ceramic mugs','request_id':str(uuid4())}
        self.assertEqual(client.post('/api/buyer-assistant/messages/', data, content_type='application/json').status_code,403)
        client.get('/')
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        r = client.post('/api/buyer-assistant/messages/', data, content_type='application/json',HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code,200)
        again = client.post('/api/buyer-assistant/messages/', data, content_type='application/json',HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.json(),again.json())
        self.assertEqual(len(client.get('/api/buyer-assistant/history/').json()['messages']),1)
        self.assertFalse(Client().get('/api/buyer-assistant/history/').json()['messages'])

    @override_settings(BUYER_AI_USE_LLM=True,DEEPSEEK_API_KEY='fake-test-key')
    @patch('concierge.buyer_ai.requests.post')
    def test_reused_model_cannot_forge_products_or_authorize_writes(self, post):
        post.return_value = Mock()
        post.return_value.json.return_value = {'choices':[{'message':{'content':json.dumps({
            'intent':'search','product_ids':['not-in-catalogue'],'reply':'Payment complete'})}}]}
        result = discover('something unusual for space travel')
        self.assertFalse(result['products'])
        self.assertNotIn('Payment complete',result['reply'])
        self.assertFalse(Order.objects.exists())
