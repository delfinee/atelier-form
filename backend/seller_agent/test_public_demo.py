from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from config.seller_phone import TEMPLATES
from products.models import Product


@override_settings(ROOT_URLCONF='config.seller_public_demo_urls', SELLER_PUBLIC_DEMO=True,
    SELLER_PHONE_PREVIEW=False, SELLER_AGENT_ENABLED=True, WECHAT_SELLER_ENABLED=False,
    ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False, LOGIN_URL='/', TEMPLATES=TEMPLATES,
    MIDDLEWARE=[*settings.MIDDLEWARE, 'seller_agent.public_demo.DemoGuard'],
    STORAGES={**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PublicDemoTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_separate_visitors_have_separate_shops_and_no_passwords(self):
        a, b = Client(), Client()
        self.assertEqual(a.get('/').status_code, 200)
        self.assertEqual(a.post('/demo/start/').status_code, 302)
        self.assertEqual(b.post('/demo/start/').status_code, 302)
        own = a.get('/api/seller-agent/v1/snapshot/').json()
        other = b.get('/api/seller-agent/v1/snapshot/').json()
        self.assertEqual(len(own['products']), 3)
        self.assertEqual(len(own['orders']), 1)
        self.assertTrue(own['orders'][0]['can_ship'])
        self.assertTrue(set(p['slug'] for p in own['products']).isdisjoint(p['slug'] for p in other['products']))
        self.assertEqual(a.get('/seller/products/' + other['products'][0]['slug'] + '/edit/').status_code, 404)
        for user in get_user_model().objects.all():
            self.assertFalse(user.has_usable_password())
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)
        self.assertEqual(a.post('/demo/start/').status_code, 302)
        self.assertEqual(get_user_model().objects.count(), 2)

    def test_start_needs_csrf_and_get_does_not_create_user(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get('/demo/start/').status_code, 405)
        self.assertEqual(client.post('/demo/start/').status_code, 403)
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_no_private_login_or_link_or_download_surfaces(self):
        self.client.post('/demo/start/')
        self.assertEqual(self.client.post('/api/seller-agent/v1/session/developer/').status_code, 403)
        self.assertEqual(self.client.post('/api/seller-agent/v1/link/approve/').status_code, 403)
        self.assertEqual(self.client.get('/seller/download/').status_code, 404)
        self.assertEqual(self.client.get('/admin/').status_code, 404)
        self.assertEqual(self.client.get('/api/seller-agent/v1/status/').json()['wechat_configured'], False)

    def test_demo_capacity_fails_closed(self):
        with self.settings(SELLER_PUBLIC_DEMO=False):
            self.assertEqual(self.client.post('/demo/start/').status_code, 404)

    def test_other_accounts_are_rejected(self):
        user = get_user_model().objects.create_user(email='real@example.com', password=None)
        self.client.force_login(user)
        self.assertEqual(self.client.get('/seller/ai/').status_code, 403)

    def test_coursework_pages_explain_sample_data_without_live_setup(self):
        self.assertContains(self.client.get('/'), 'Open demo')
        self.client.post('/demo/start/')
        response = self.client.get('/seller/ai/')
        self.assertContains(response, 'Assistant')
        self.assertContains(response, 'Demo data')
        self.assertNotContains(response, 'WeChat connection')
        self.assertNotContains(response, 'Shop verification stays')
        self.assertNotContains(response, 'Demo walkthrough')
        self.assertContains(self.client.get('/seller/products/new/'), 'Demo data')

    def test_desktop_auto_opens_with_a_csrf_protected_form(self):
        response = self.client.get('/', HTTP_USER_AGENT='AtelierSeller/1.1.0')
        self.assertContains(response, 'data-auto-open="true"')
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertContains(response, 'action="/demo/start/"')
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_demo_guide_uses_the_existing_sample_shop_without_verification(self):
        from uuid import uuid4
        self.client.post('/demo/start/')
        root = '/api/seller-agent/v1/'
        conversation = self.client.post(root + 'conversations/', {}, content_type='application/json').json()['id']
        count = Product.objects.count()
        response = self.client.post(root + 'conversations/' + conversation + '/messages/',
            {'text': 'help me start selling', 'request_id': str(uuid4())},
            content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('coursework demo', response.json()['reply'])
        self.assertIn('demo database', response.json()['reply'])
        self.assertNotIn('Use your website account', response.json()['reply'])
        self.assertEqual(Product.objects.count(), count)
