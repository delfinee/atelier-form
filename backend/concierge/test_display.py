import json
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from frontend.mockdata.makers import MAKERS_BY_SLUG
from frontend.mockdata.products import PRODUCTS_BY_SLUG
from orders.tests.factories import make_category, make_maker
from products.models import Product, ProductVariant
from reviews.models import Review
from .display import localize_catalogue_text, localize_reviews
from .shopping import discover


@override_settings(BUYER_AI_USE_LLM=False)
class ShoppingDisplayLanguageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed = PRODUCTS_BY_SLUG['woven-cotton-throw']
        maker = make_maker('lu-wenjing', MAKERS_BY_SLUG['lu-wenjing']['name'])
        cls.product = Product.objects.create(slug=seed['slug'], name=seed['name'],
            maker=maker, category=make_category('textiles', 'Textiles'),
            materials=seed['materials'], price='128', stock_quantity=2)
        cls.variant = ProductVariant.objects.create(product=cls.product,
            label='Indigo', sku='LANGUAGE-INDIGO', stock_quantity=2)
        cls.review = Review.objects.create(product=cls.product,
            user=get_user_model().objects.create_user(email='review-language@example.test'),
            rating=5, title='True to listing', body='Recommended!')

    def setUp(self):
        cache.clear()

    def test_chinese_result_translates_every_display_field_without_changing_records(self):
        result = discover('只看蓝色的商品', action='blue', language='zh-hans')
        result = discover('看看评价', result['context'], action='reviews', language='zh-hans')
        card = result['products'][0]
        self.assertEqual(card['name'], '手织纯棉四季毯')
        self.assertEqual(card['maker'], '陆文静')
        self.assertEqual(card['options'][0]['label'], '蓼蓝')
        self.assertTrue(all(not any(c.isascii() and c.isalpha() for c in material)
                            for material in card['materials']))
        review = card['review_examples'][0]
        self.assertEqual(review['title'], '与商品描述一致')
        self.assertEqual(review['body'], '推荐！')
        self.assertTrue(review['is_translation'])
        self.assertEqual((card['rating'], card['review_count'], card['price']), (5.0, 1, '128.00'))
        self.review.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.review.body, 'Recommended!')
        self.assertEqual(self.product.name, 'Woven Cotton Throw')

    def test_english_mode_keeps_original_english_content(self):
        result = discover('Reviews', action='reviews', language='en')
        card = result['products'][0]
        self.assertEqual(card['name'], 'Woven Cotton Throw')
        self.assertEqual(card['maker'], 'Lu Wenjing')
        self.assertEqual(card['options'][0]['label'], 'Indigo')
        self.assertEqual(card['review_examples'][0]['body'], 'Recommended!')

    def test_reload_repairs_old_cached_messages_without_clearing_history(self):
        response = discover('Reviews', action='reviews', language='en')
        session = self.client.session
        session['buyer_assistant_languages'] = {'zh-hans': {
            'context': {'language': 'zh'}, 'responses': {},
            'history': [{'text': '看看评价', 'response': response}]}}
        session.save()
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'zh-hans'
        history = self.client.get('/api/buyer-assistant/history/').json()['messages']
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['text'], '看看评价')
        self.assertEqual(history[0]['response']['products'][0]['name'], '手织纯棉四季毯')
        self.assertEqual(history[0]['response']['products'][0]['review_examples'][0]['body'], '推荐！')

    @override_settings(DEEPSEEK_API_KEY='test-only-key', SELLER_AGENT_MODEL='deepseek-flash')
    @patch('concierge.display.requests.post')
    def test_other_public_reviews_translate_once_and_cache_by_content(self, post):
        post.return_value = Mock()
        post.return_value.json.return_value = {'choices': [{'message': {'content':
            json.dumps({'translations': ['织物边缘有些粗糙。']})}}]}
        def cards():
            return [{'review_examples': [{'title': '', 'body': 'The fabric has a rough edge.', 'rating': 3}]}]
        first = localize_reviews(cards(), 'zh-hans')
        second = localize_reviews(cards(), 'zh-hans')
        self.assertEqual(first[0]['review_examples'][0]['body'], '织物边缘有些粗糙。')
        self.assertEqual(first, second)
        post.assert_called_once()
        self.assertEqual(json.loads(post.call_args.kwargs['json']['messages'][1]['content']),
                         ['The fabric has a rough edge.'])

    @override_settings(DEEPSEEK_API_KEY='test-only-key')
    @patch('concierge.display.requests.post')
    def test_chinese_reviews_translate_to_english_too(self, post):
        post.return_value = Mock()
        post.return_value.json.return_value = {'choices': [{'message': {'content':
            json.dumps({'translations': ['The fabric is soft.']})}}]}
        cards = [{'review_examples': [{'title': '', 'body': '织物柔软。', 'rating': 4}]}]
        self.assertEqual(localize_reviews(cards, 'en')[0]['review_examples'][0]['body'],
                         'The fabric is soft.')

    @override_settings(DEEPSEEK_API_KEY='test-only-key')
    @patch('concierge.display.requests.post')
    def test_custom_product_labels_also_follow_the_selected_language(self, post):
        post.return_value = Mock()
        post.return_value.json.return_value = {'choices': [{'message': {'content': json.dumps({
            'translations': ['窗帘布托特包', '测试工作室', '再生织物', '天空蓝']})}}]}
        cards = [{'name': 'Custom Curtain Tote Bag', 'maker': 'Test Studio',
                  'materials': ['Reclaimed fabric'], 'options': [{'label': 'Sky blue'}]}]
        localize_catalogue_text(cards, 'zh-hans')
        self.assertEqual(cards[0]['name'], '窗帘布托特包')
        self.assertEqual(cards[0]['maker'], '测试工作室')
        self.assertEqual(cards[0]['materials'], ['再生织物'])
        self.assertEqual(cards[0]['options'][0]['label'], '天空蓝')

    @override_settings(DEEPSEEK_API_KEY='test-only-key')
    @patch('concierge.display.requests.post')
    def test_failed_translation_does_not_invent_a_review_or_mix_languages(self, post):
        import requests
        post.side_effect = requests.Timeout()
        cards = [{'review_examples': [{'title': '', 'body': 'Unusual original review.', 'rating': 2}]}]
        review = localize_reviews(cards, 'zh-hans')[0]['review_examples'][0]
        self.assertEqual(review['body'], '评价翻译暂不可用。')
        self.assertEqual(review['rating'], 2)
