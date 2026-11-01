from unittest.mock import Mock, patch
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils.translation import override

from concierge.shopping import discover
from frontend.forms_seller import SellerProductForm
from orders.tests.factories import make_category, make_maker, make_product
from . import planner

BASE = '/api/seller-agent/v1/'


@override_settings(
    ALLOWED_HOSTS=['school.test'], SELLER_SHARED_DEMO_HOSTS=['school.test'],
    SELLER_AGENT_ENABLED=True, SELLER_AGENT_USE_LLM=False, SECURE_SSL_REDIRECT=False,
    STORAGES={**settings.STORAGES, 'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
)
class LanguageConsistencyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = make_category('ceramics', 'Ceramics')
        cls.product = make_product(maker=make_maker("language-maker", "Language Maker"), category=category,
                                   name='Original Mug', slug='original-mug', stock_quantity=7)

    def setUp(self):
        cache.clear()
        self.client = Client(HTTP_HOST='school.test')

    def language(self, code):
        response = self.client.post('/i18n/setlang/', {'language': code, 'next': '/seller/ai/'})
        self.assertEqual(response.status_code, 302)

    def conversation(self):
        response = self.client.post(BASE + 'conversations/', {}, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        return response.json()['id']

    def test_one_selector_changes_seller_desk_and_editor(self):
        self.language('zh-hans')
        self.assertContains(self.client.get('/seller/ai/'), '卖家助手')
        self.assertContains(self.client.get('/seller/products/'), '主站商品')
        self.assertContains(self.client.get('/seller/products/original-mug/edit/'), '保存商品')
        self.language('en')
        self.assertContains(self.client.get('/seller/ai/'), 'Seller assistant')
        self.assertContains(self.client.get('/seller/products/'), 'Main website products')
        self.assertContains(self.client.get('/seller/products/original-mug/edit/'), 'Save product')

    def test_seller_histories_are_separate_by_selected_language(self):
        self.language('en')
        english = self.conversation()
        self.language('zh-hans')
        chinese = self.conversation()
        response = self.client.get(BASE + 'conversations/').json()['conversations']
        self.assertEqual([row['id'] for row in response], [chinese])
        self.language('en')
        self.assertEqual([row['id'] for row in self.client.get(BASE + 'conversations/').json()['conversations']], [english])

    def test_english_command_uses_chinese_selected_interface(self):
        self.language('zh-hans')
        conversation = self.conversation()
        response = self.client.post(BASE + f'conversations/{conversation}/messages/',
            {'text': 'help me start selling', 'request_id': str(uuid4())}, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('无需登录', response.json()['reply'])
        self.assertNotIn('This is a shared school demo', response.json()['reply'])

    def test_chinese_stock_preview_has_same_data_and_localized_summary(self):
        self.language('zh-hans')
        conversation = self.conversation()
        response = self.client.post(BASE + f'conversations/{conversation}/changes/',
            {'request_id': str(uuid4()), 'action': 'stock', 'target': self.product.slug,
             'values': {'quantity': 9}}, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('可售库存', response.json()['summary'])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 7)
        self.assertEqual(self.product.name, 'Original Mug')

    def test_form_labels_placeholders_and_choices_follow_locale(self):
        with override('zh-hans'):
            form = SellerProductForm()
            self.assertEqual(form.fields['name'].label, '名称')
            self.assertIn('例如', form.fields['name'].widget.attrs['placeholder'])
        with override('en'):
            self.assertEqual(SellerProductForm().fields['name'].label, 'Name')

    def test_shopping_reply_follows_selected_locale_not_query_language(self):
        with override('zh-hans'):
            chinese = discover('Show me mugs', language='zh-hans')
        with override('en'):
            english = discover('我想看看杯子', language='en')
        self.assertEqual(chinese['context']['language'], 'zh')
        self.assertEqual(english['context']['language'], 'en')
        self.assertRegex(chinese['reply'], r'[\u4e00-\u9fff]')
        self.assertNotRegex(english['reply'], r'[\u4e00-\u9fff]')

    @override_settings(SELLER_AGENT_USE_LLM=True, SELLER_AGENT_API_KEY='test-only',
                       SELLER_AGENT_LLM_DAILY_LIMIT=500)
    @patch('seller_agent.planner.requests.post')
    def test_deepseek_receives_selected_response_language(self, post):
        response = Mock()
        response.json.return_value = {'choices': [{'message': {'content':
            '{"intent":"help","reply":"请先查看库存。"}'}}]}
        post.return_value = response
        result = planner.plan('What should I do next?', {}, [], language='zh-hans')
        self.assertEqual(result['engine'], 'deepseek')
        self.assertIn('Simplified Chinese', post.call_args.kwargs['json']['messages'][0]['content'])
