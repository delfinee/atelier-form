from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command, CommandError
from django.test import Client, TestCase, override_settings
from config.seller_phone import TEMPLATES as PHONE_TEMPLATES
from orders.tests.factories import make_seller_user
from products.models import Maker


@override_settings(ROOT_URLCONF='config.seller_production_urls', DEBUG=False,
    ALLOWED_HOSTS=['seller.example.com'], SELLER_AGENT_ENABLED=True, WECHAT_SELLER_ENABLED=True,
    WECHAT_SELLER_DEV_LOGIN=False, SELLER_PRODUCTION=True, SELLER_PHONE_PREVIEW=False,
    SECURE_SSL_REDIRECT=False, LOGIN_URL='/account/login/', LOGIN_REDIRECT_URL='/seller/ai/',
    TEMPLATES=PHONE_TEMPLATES, SELLER_OPERATOR='Test operator', SELLER_CONTACT_EMAIL='support@example.com',
    MIDDLEWARE=[*settings.MIDDLEWARE, 'seller_agent.release_views.PrivateResponses'],
    STORAGES={**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ReleaseViewsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(HTTP_HOST='seller.example.com')

    def test_public_information_does_not_require_authentication(self):
        for path in ('/', '/privacy/'):
            response = self.client.get(path, secure=True)
            self.assertContains(response, 'support@example.com')
            self.assertNotContains(response, 'demo-seller-2026')
        self.assertEqual(self.client.get('/healthz/', secure=True).json(), {'ok': True})

    def test_health_hides_database_exception(self):
        with patch('seller_agent.release_views.connection.cursor', side_effect=RuntimeError('private credentials')):
            response = self.client.get('/healthz/', secure=True)
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, 'credentials', status_code=503)

    def test_release_does_not_offer_download_or_developer_pages(self):
        user = make_seller_user('release@example.com')
        self.client.force_login(user)
        for path in ('/seller/download/', '/seller/ai/mini-preview/', '/admin/', '/checkout/'):
            self.assertEqual(self.client.get(path, secure=True).status_code, 404)
        response = self.client.get('/seller/ai/', secure=True)
        self.assertContains(response, '/seller/products/')
        self.assertNotContains(response, '/seller/download/')
        self.assertNotContains(response, '/seller/ai/mini-preview/')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow')
        self.assertEqual(self.client.post('/api/seller-agent/v1/session/developer/', {}, secure=True).status_code, 403)

    def test_login_is_rate_limited_by_real_client(self):
        for _ in range(20):
            self.assertEqual(self.client.post('/account/login/', {'username':'missing@example.com','password':'wrong'}, secure=True,
                HTTP_X_FORWARDED_FOR='192.0.2.10').status_code, 200)
        self.assertEqual(self.client.post('/account/login/', {}, secure=True, HTTP_X_FORWARDED_FOR='192.0.2.10').status_code, 429)
        self.assertEqual(self.client.post('/account/login/', {}, secure=True, HTTP_X_FORWARDED_FOR='192.0.2.11').status_code, 200)


class ProvisionSellerTests(TestCase):
    def test_existing_user_password_and_privileges_never_changed(self):
        user = get_user_model().objects.create_user(email='existing@example.com', password='original-password')
        with TemporaryDirectory() as directory:
            password_file = Path(directory) / 'password'
            password_file.write_text('Unique-Review-Password-6472')
            with self.assertRaises(CommandError):
                call_command('provision_seller', email=user.email, shop='New shop', password_file=password_file, stdout=StringIO())
        user.refresh_from_db()
        self.assertFalse(user.is_seller)
        self.assertTrue(user.check_password('original-password'))
        self.assertFalse(Maker.objects.filter(owner=user).exists())

    def test_new_seller_is_scoped_to_one_new_shop_without_admin(self):
        with TemporaryDirectory() as directory:
            password_file = Path(directory) / 'password'
            password_file.write_text('Unique-Review-Password-6472')
            call_command('provision_seller', email='new@example.com', shop='New shop', password_file=password_file, stdout=StringIO())
        user = get_user_model().objects.get(email='new@example.com')
        self.assertTrue(user.is_seller)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(Maker.objects.filter(owner=user).count(), 1)

    def test_review_records_stay_in_separate_new_shop_and_are_labelled(self):
        from orders.models import Order
        from products.models import Product
        with TemporaryDirectory() as directory:
            password_file = Path(directory) / 'password'
            password_file.write_text('Unique-Review-Password-6472')
            call_command('provision_seller', email='review@example.com', shop='Review only',
                         password_file=password_file, review_fixtures=True, stdout=StringIO())
        product = Product.objects.get(maker__owner__email='review@example.com')
        self.assertTrue(product.name.startswith('REVIEW TEST'))
        self.assertFalse(product.is_active)
        order = Order.objects.get(items__product=product)
        self.assertTrue(order.order_number.startswith('REVIEW-TEST-'))
        self.assertEqual(order.shipping_address_snapshot['address_line_1'], 'TEST ONLY - DO NOT SHIP')
