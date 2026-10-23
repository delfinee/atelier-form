import json
from unittest.mock import Mock, patch
from uuid import uuid4

import requests
from django.conf import settings
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings

from accounts.models import User
from orders.models import Order
from products.models import Category, Maker, Product, ProductVariant
from reviews.models import Review
from . import buyer_ai
from .shopping import discover


def response(payload):
    result = Mock()
    result.json.return_value = {'choices': [{'message': {'content': json.dumps(payload)}}]}
    return result


CHOICES = {'types': ['mug', 'bowl'], 'materials': ['ceramic', 'cotton'], 'colours': ['blue', 'white']}
FACTS = [{'id': 'mug', 'name': 'Blue mug', 'price': '30.00', 'currency': 'CNY'}]


@override_settings(BUYER_AI_USE_LLM=True, DEEPSEEK_API_KEY='test-key',
                   DEEPSEEK_MODEL='deepseek-flash', BUYER_AI_DAILY_LIMIT=500)
class BuyerModelValidationTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch('concierge.buyer_ai.requests.post')
    def test_semantic_request_uses_model_and_bounded_public_context(self, post):
        post.return_value = response({'intent': 'search', 'filters': {'types': ['mug'], 'max_price': '35'},
                                      'product_ids': ['mug'], 'reply': 'Here is a handmade gift idea.'})
        history = [{'text': 'I need a gift', 'response': {'products': [{'slug': 'mug'}],
                    'private_account': 'never-forward'}}]
        result, problem = buyer_ai.interpret('Something for a coffee lover?', {}, FACTS, history, CHOICES)
        self.assertEqual(result['selection'], ['mug'])
        self.assertEqual(result['filters']['max_price'], '35')
        sent = post.call_args.kwargs['json']['messages'][-1]['content']
        self.assertNotIn('never-forward', sent)
        self.assertNotIn('test-key', sent)
        self.assertFalse(problem)

    @patch('concierge.buyer_ai.requests.post')
    def test_rejects_unknown_ids_filters_and_write_fields(self, post):
        for payload in [
            {'intent': 'search', 'product_ids': ['invented']},
            {'intent': 'search', 'filters': {'colours': ['purple']}},
            {'intent': 'search', 'filters': {'max_price': '-1'}},
            {'intent': 'search', 'filters': {'max_price': 'NaN'}},
            {'intent': 'search', 'filters': {'seller_id': 99}},
            {'intent': 'search', 'confirmed': True},
        ]:
            post.return_value = response(payload)
            result, problem = buyer_ai.interpret('Find a gift', {}, FACTS, [], CHOICES)
            self.assertIsNone(result)
            self.assertEqual(problem, 'unavailable')

    @patch('concierge.buyer_ai.requests.post')
    def test_model_prose_cannot_supply_prices_or_claim_payment(self, post):
        for text in ('It costs CNY 1.00 and has 999 reviews.', 'Payment complete', 'I have paid your order.'):
            post.return_value = response({'intent': 'search', 'reply': text})
            result, problem = buyer_ai.interpret('Show me a mug', {}, FACTS, [], CHOICES)
            self.assertEqual(result['reply'], '')
            self.assertFalse(problem)

    @patch('concierge.buyer_ai.requests.post')
    def test_timeout_and_malformed_json_fall_back(self, post):
        post.side_effect = requests.Timeout()
        self.assertEqual(buyer_ai.interpret('Hi', {}, FACTS, [], CHOICES), (None, 'unavailable'))
        post.side_effect = None
        post.return_value = response({})
        self.assertEqual(buyer_ai.interpret('Hi', {}, FACTS, [], CHOICES), (None, 'unavailable'))

    @override_settings(BUYER_AI_DAILY_LIMIT=1)
    @patch('concierge.buyer_ai.requests.post')
    def test_daily_allowance_bounds_cost(self, post):
        post.return_value = response({'intent': 'advice', 'reply': 'Start with the recipient\'s preferences.'})
        self.assertIsNotNone(buyer_ai.interpret('Gift advice?', {}, FACTS, [], CHOICES)[0])
        self.assertEqual(buyer_ai.interpret('More advice?', {}, FACTS, [], CHOICES), (None, 'quota'))
        self.assertEqual(post.call_count, 1)


@override_settings(BUYER_AI_USE_LLM=True, DEEPSEEK_API_KEY='test-key',
                   DEEPSEEK_MODEL='deepseek-flash', BUYER_AI_DAILY_LIMIT=500,
                   SECURE_SSL_REDIRECT=False,
                   STORAGES={**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class BuyerModelIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name='Ceramics', slug='ai-ceramics')
        cls.maker = Maker.objects.create(name='Studio', slug='ai-studio')
        cls.blue = Product.objects.create(name='Blue ceramic mug', slug='ai-blue-mug',
            category=cls.category, maker=cls.maker, price='30', stock_quantity=5,
            currency='CNY', materials=['Stoneware'])
        cls.white = Product.objects.create(name='White ceramic mug', slug='ai-white-mug',
            category=cls.category, maker=cls.maker, price='15', stock_quantity=5, currency='CNY')
        cls.hidden = Product.objects.create(name='Hidden private mug', slug='ai-hidden',
            category=cls.category, maker=cls.maker, price='1', is_active=False)
        cls.reviewer = User.objects.create_user(email='buyer-model-reviewer@example.invalid')
        Review.objects.create(product=cls.blue, user=cls.reviewer, rating=5, is_published=True)

    def setUp(self):
        cache.clear()

    @patch('concierge.buyer_ai.requests.post')
    def test_natural_query_filters_fresh_facts_not_model_prices(self, post):
        post.return_value = response({'intent': 'search', 'filters': {'types': ['mug'], 'max_price': '35',
            'min_rating': 4}, 'reply': 'I picked pieces with published feedback.'})
        result = discover('I need a well-loved present for a coffee lover')
        self.assertEqual(result['engine'], 'deepseek')
        self.assertEqual([p['slug'] for p in result['products']], ['ai-blue-mug'])
        self.assertEqual(result['products'][0]['price'], '30.00')
        self.assertEqual(result['products'][0]['rating'], 5)
        sent = post.call_args.kwargs['json']['messages'][-1]['content']
        self.assertNotIn('ai-hidden', sent)
        self.assertNotIn('buyer-model-reviewer', sent)

    @patch('concierge.buyer_ai.requests.post')
    def test_chinese_followup_and_comparison_use_live_values(self, post):
        post.return_value = response({'intent': 'search', 'filters': {'types': ['mug']}})
        first = discover('我想给爱喝咖啡的朋友买礼物')
        Product.objects.filter(pk=self.blue.pk).update(price='31.50')
        post.return_value = response({'intent': 'compare', 'filters': {'types': ['mug']},
            'product_ids': ['ai-blue-mug', 'ai-white-mug'], 'details': ['price', 'reviews'],
            'reply': '可以，我们比较实际价格和已有评价。'})
        result = discover('比较一下这两件的价格和评价', first['context'])
        self.assertIn('31.50', result['reply'])
        self.assertIn('暂无已发布评价', result['reply'])
        self.assertEqual(result['engine'], 'deepseek')

    @patch('concierge.buyer_ai.requests.post')
    def test_model_cannot_bypass_variant_price_or_currency(self, post):
        ProductVariant.objects.create(product=self.blue, label='Blue', sku='BUYER-AI-BLUE',
            price_override='40', stock_quantity=2)
        ProductVariant.objects.create(product=self.blue, label='White', sku='BUYER-AI-WHITE',
            price_override='10', stock_quantity=5)
        post.return_value = response({'intent': 'search', 'filters': {'colours': ['blue'],
            'max_price': '35', 'currency': 'CNY'}, 'product_ids': ['ai-blue-mug']})
        self.assertFalse(discover('A blue one within my budget')['products'])

    @patch('concierge.buyer_ai.requests.post')
    def test_refreshes_prices_after_provider_returns(self, post):
        def changed_during_call(*args, **kwargs):
            Product.objects.filter(pk=self.blue.pk).update(price='45')
            return response({'intent': 'search', 'filters': {'max_price': '35'},
                             'product_ids': ['ai-blue-mug']})
        post.side_effect = changed_during_call
        self.assertFalse(discover('A gift below my budget')['products'])

    @patch('concierge.buyer_ai.requests.post')
    def test_advice_and_unsupported_requests_do_not_write(self, post):
        for payload in ({'intent': 'advice', 'reply': 'Consider the recipient\'s preferred colours.'},
                        {'intent': 'unsupported', 'reply': 'Payment complete'}):
            post.return_value = response(payload)
            result = discover('Please help me with this purchase')
            self.assertFalse(result['products'])
            self.assertNotIn('Payment complete', result['reply'])
            self.assertFalse(Order.objects.exists())
            self.blue.refresh_from_db()
            self.assertEqual(self.blue.stock_quantity, 5)

    @patch('concierge.buyer_ai.requests.post')
    def test_failure_retains_working_catalogue_search(self, post):
        post.side_effect = requests.Timeout()
        result = discover('Find ceramic mugs')
        self.assertEqual(result['engine'], 'guided')
        self.assertEqual(len(result['products']), 2)
        self.assertIn('temporarily unavailable', result['notice'])

    @patch('concierge.buyer_ai.requests.post')
    def test_session_retry_does_not_spend_twice_and_mode_is_visible(self, post):
        post.return_value = response({'intent': 'search', 'filters': {'types': ['mug']}})
        client = Client(enforce_csrf_checks=True)
        client.get('/')
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        data = {'text': 'A present for a coffee lover please', 'request_id': str(uuid4())}
        kwargs = {'content_type': 'application/json', 'HTTP_X_CSRFTOKEN': token}
        first = client.post('/api/buyer-assistant/messages/', data, **kwargs)
        second = client.post('/api/buyer-assistant/messages/', data, **kwargs)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(post.call_count, 1)
        self.assertTrue(client.get('/api/buyer-assistant/history/').json()['ai_enabled'])
        self.assertFalse(Client().get('/api/buyer-assistant/history/').json()['messages'])
