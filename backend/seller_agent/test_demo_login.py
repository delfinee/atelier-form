from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.test import Client, TestCase, override_settings

from accounts.demo import DEMO_SELLER, DEMO_SELLER_NAME, sync_demo_seller_name
from orders.tests.factories import make_category, make_maker, make_product, make_seller_user
from products.models import Product


@override_settings(
    SELLER_SHARED_DEMO_ENABLED=False, SELLER_SHARED_DEMO_HOSTS=['school.test'],
    ALLOWED_HOSTS=['school.test', 'testserver'], SELLER_AGENT_ENABLED=True,
    SELLER_AGENT_USE_LLM=False, SELLER_AGENT_API_KEY='', SECURE_SSL_REDIRECT=False,
    STORAGES={**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
)
class DemoSellerLoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = make_seller_user(DEMO_SELLER['email'])
        cls.seller.set_password(DEMO_SELLER['password'])
        cls.seller.first_name, cls.seller.last_name = 'Meilin', 'Chen'
        cls.seller.save()
        cls.maker = make_maker('chen-meilin', 'Chen Meilin', owner=cls.seller)
        category = make_category()
        cls.own_product = make_product(maker=cls.maker, category=category, slug='demo-login-mug')
        cls.other_product = make_product(maker=make_maker('other-login-maker', 'Other maker'),
                                         category=category, slug='other-login-mug')

    def setUp(self):
        self.client = Client(HTTP_HOST='school.test', HTTP_USER_AGENT='Mozilla/5.0 AtelierSeller/1.4.0')

    def test_demo_login_is_prefilled_without_automatically_signing_in(self):
        response = self.client.get('/account/login/', HTTP_ACCEPT_LANGUAGE='zh-hans')
        self.assertContains(response, 'value="seller@atelierform.test"')
        self.assertContains(response, 'value="demo-seller-2026"')
        self.assertContains(response, 'chen mei lin')
        self.assertContains(response, '点击登录即可继续')
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_prefilled_values_sign_in_to_real_account_and_keep_shared_catalogue(self):
        sync_demo_seller_name()
        before = self.client.get('/api/seller-agent/v1/snapshot/').json()
        page = self.client.get('/account/login/')
        response = self.client.post('/account/login/', {
            'email': page.context['values']['email'], 'password': page.context['demo_password']})
        self.assertRedirects(response, '/seller/ai/', fetch_redirect_response=False)
        self.assertEqual(self.client.session[SESSION_KEY], str(self.seller.pk))
        me = self.client.get('/api/seller-agent/v1/me/').json()
        self.assertEqual(me['account'], DEMO_SELLER['email'])
        self.assertEqual(me['seller_name'], DEMO_SELLER_NAME)
        after = self.client.get('/api/seller-agent/v1/snapshot/').json()
        self.assertEqual({p['slug'] for p in before['products']}, {p['slug'] for p in after['products']})
        self.assertEqual(Product.objects.get(pk=self.own_product.pk).maker_id, self.maker.pk)
        self.assertContains(self.client.get('/seller/ai/'), DEMO_SELLER_NAME)

    def test_prefill_is_not_exposed_on_website_other_hosts_or_registration(self):
        for client, path in ((Client(HTTP_HOST='school.test'), '/account/login/'),
                             (Client(HTTP_HOST='school.test'), '/account/login/?next=/seller/ai/'),
                             (Client(HTTP_HOST='school.test'), '/account/login/?app=seller'),
                             (Client(HTTP_HOST='testserver', HTTP_USER_AGENT='AtelierSeller/1.4.0'), '/account/login/'),
                             (self.client, '/account/register/')):
            response = client.get(path)
            self.assertNotContains(response, DEMO_SELLER['email'])
            self.assertNotContains(response, DEMO_SELLER['password'])

    def test_invalid_post_keeps_entered_email_and_never_echoes_password(self):
        response = self.client.post('/account/login/', {'email': 'mistyped@example.test', 'password': 'bad-entry'})
        self.assertContains(response, 'value="mistyped@example.test"')
        self.assertNotContains(response, 'value="demo-seller-2026"')
        self.assertNotContains(response, 'bad-entry')
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_login_still_requires_csrf(self):
        client = Client(HTTP_HOST='school.test', HTTP_USER_AGENT='AtelierSeller/1.4.0', enforce_csrf_checks=True)
        credentials = {k: DEMO_SELLER[k] for k in ('email', 'password')}
        self.assertEqual(client.post('/account/login/', credentials).status_code, 403)
        client.get('/account/login/')
        credentials['csrfmiddlewaretoken'] = client.cookies[settings.CSRF_COOKIE_NAME].value
        self.assertEqual(client.post('/account/login/', credentials).status_code, 302)
        self.assertEqual(client.session[SESSION_KEY], str(self.seller.pk))

    def test_demo_login_link_only_appears_in_seller_app(self):
        browser = Client(HTTP_HOST='school.test')
        self.assertNotContains(browser.get('/seller/ai/'), 'Sign in as demo seller')
        self.assertContains(self.client.get('/seller/ai/'), 'Sign in as demo seller')

    def test_prefill_fails_closed_when_account_is_privileged_or_password_changed(self):
        for flag in ('is_staff', 'is_admin', 'is_superuser'):
            setattr(self.seller, flag, True)
            self.seller.save()
            self.assertNotContains(self.client.get('/account/login/'), 'value="demo-seller-2026"')
            setattr(self.seller, flag, False)
        self.seller.set_password('different-password')
        self.seller.save()
        self.assertNotContains(self.client.get('/account/login/'), 'value="demo-seller-2026"')

    def test_rename_only_updates_existing_demo_profile_without_resetting_records(self):
        password_hash = self.seller.password
        self.assertTrue(sync_demo_seller_name())
        self.assertTrue(sync_demo_seller_name())
        self.seller.refresh_from_db()
        self.maker.refresh_from_db()
        self.assertEqual(self.seller.full_name, DEMO_SELLER_NAME)
        self.assertEqual(self.maker.name, DEMO_SELLER_NAME)
        self.assertEqual(self.seller.password, password_hash)
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(self.maker.owner_id, self.seller.pk)

    def test_rename_does_not_touch_privileged_or_unlinked_account(self):
        self.seller.is_staff = True
        self.seller.save()
        self.assertFalse(sync_demo_seller_name())
        self.seller.is_staff = False
        self.seller.save()
        self.maker.owner = None
        self.maker.save()
        self.assertFalse(sync_demo_seller_name())
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.first_name, 'Meilin')
