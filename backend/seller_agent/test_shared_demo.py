from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from orders.tests.factories import (
    make_bare_order, make_buyer, make_category, make_maker,
    make_order_item, make_product, make_seller_user,
)
from products.models import Product, ProductImage

BASE = '/api/seller-agent/v1/'


@override_settings(
    SELLER_SHARED_DEMO_ENABLED=False,
    SELLER_SHARED_DEMO_HOSTS=['school.test'],
    ALLOWED_HOSTS=['school.test', 'testserver'],
    SELLER_AGENT_ENABLED=True, SELLER_AGENT_USE_LLM=False, SELLER_AGENT_API_KEY='',
    SECURE_SSL_REDIRECT=False,
    STORAGES={**settings.STORAGES, 'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
)
class SharedCatalogueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = make_seller_user('original@school.test')
        cls.maker = make_maker('original-maker', 'Original maker', owner=cls.seller)
        cls.category = make_category('ceramics', 'Ceramics')
        cls.product = make_product(maker=cls.maker, category=cls.category,
            slug='original-mug', name='Original Mug', stock_quantity=17)
        cls.image = ProductImage.objects.create(product=cls.product, image='original.jpg')
        other = make_maker('second-maker', 'Second maker')
        cls.other = make_product(maker=other, category=cls.category,
            slug='original-bowl', name='Original Bowl')
        order = make_bare_order()
        make_order_item(order=order, product=cls.product)

    def setUp(self):
        cache.clear()
        self.client = Client(HTTP_HOST='school.test')

    def post(self, path, data, client=None):
        return (client or self.client).post(path, data, content_type='application/json')

    def conversation(self):
        response = self.post(BASE + 'conversations/', {})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()['id']

    def test_reads_original_catalogue_across_makers_without_copying(self):
        before = Product.objects.count()
        response = self.client.get(BASE + 'snapshot/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual({p['slug'] for p in response.json()['products']},
                         {'original-mug', 'original-bowl'})
        self.assertEqual(response.json()['orders'], [])
        self.assertEqual(Product.objects.count(), before)
        self.product.refresh_from_db()
        self.assertEqual(self.product.maker, self.maker)
        self.assertEqual(self.product.stock_quantity, 17)
        self.assertTrue(ProductImage.objects.filter(pk=self.image.pk).exists())
        page = self.client.get('/seller/products/')
        self.assertContains(page, 'Original Mug')
        self.assertContains(page, 'Original Bowl')
        self.assertContains(page, 'Main website products')
        self.assertNotContains(page, 'Sign in')

    def test_stock_confirmation_updates_same_original_row_and_preserves_owner(self):
        conversation = self.conversation()
        response = self.post(BASE + f'conversations/{conversation}/changes/', {
            'request_id': str(uuid4()), 'action': 'stock',
            'target': self.product.slug, 'values': {'quantity': 23}})
        self.assertEqual(response.status_code, 200, response.content)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 17)
        change = response.json()['id']
        response = self.post(BASE + f'changes/{change}/confirm/', {'confirmed': True})
        self.assertEqual(response.status_code, 200, response.content)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 23)
        self.assertEqual(self.product.maker, self.maker)
        self.assertEqual(Product.objects.count(), 2)

    def test_new_draft_and_publication_are_visible_to_separate_visitor(self):
        conversation = self.conversation()
        response = self.post(BASE + f'conversations/{conversation}/changes/', {
            'request_id': str(uuid4()), 'action': 'listing', 'target': '',
            'values': {'name': 'Team Mug', 'category': 'ceramics',
                'description': 'Coursework test mug', 'price': '25.00', 'quantity': 0}})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Product.objects.count(), 2)
        response = self.post(BASE + f"changes/{response.json()['id']}/confirm/", {'confirmed': True})
        self.assertEqual(response.status_code, 200, response.content)
        product = Product.objects.get(name='Team Mug')
        self.assertFalse(product.is_active)
        public = Client(HTTP_HOST='testserver')
        self.assertEqual(public.get('/api/products/' + product.slug + '/').status_code, 404)
        # Same publication endpoint used by the product editor, without a login.
        response = self.client.patch('/api/seller/products/' + product.slug + '/',
            {'is_active': True}, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(public.get('/api/products/' + product.slug + '/').status_code, 200)
        self.assertEqual(Client(HTTP_HOST='school.test').get(BASE + 'snapshot/').status_code, 200)

    def test_original_editor_and_product_api_preserve_maker(self):
        self.assertEqual(self.client.get('/seller/products/original-mug/edit/').status_code, 200)
        response = self.client.patch('/api/seller/products/original-mug/',
            {'price': '22.00', 'maker': 9999}, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.product.refresh_from_db()
        self.assertEqual(self.product.maker, self.maker)
        self.assertEqual(str(self.product.price), '22.00')

    def test_no_login_account_is_unprivileged_and_does_not_replace_buyer_session(self):
        buyer = make_buyer('visitor@school.test')
        self.client.force_login(buyer)
        self.assertEqual(self.client.get('/seller/ai/').status_code, 200)
        self.assertEqual(int(self.client.session['_auth_user_id']), buyer.pk)
        actor = get_user_model().objects.get(email=settings.SELLER_SHARED_DEMO_EMAIL)
        self.assertFalse(actor.has_usable_password())
        self.assertFalse(actor.is_staff or actor.is_superuser or actor.is_admin)
        self.assertIn(self.client.get('/api/admin/products/').status_code, (401, 403))
        self.assertEqual(self.post(BASE + 'link/start/', {}).status_code, 403)

    def test_other_hosts_still_require_login_and_normal_sellers_are_scoped(self):
        visitor = Client(HTTP_HOST='testserver')
        self.assertEqual(visitor.get('/seller/ai/').status_code, 302)
        self.assertIn(visitor.get(BASE + 'snapshot/').status_code, (401, 403))
        visitor.force_login(self.seller)
        products = visitor.get(BASE + 'snapshot/').json()['products']
        self.assertEqual([p['slug'] for p in products], ['original-mug'])
        self.assertNotIn('No login', visitor.get(BASE + 'me/').json()['onboarding'])

    def test_csrf_remains_required_without_login(self):
        visitor = Client(HTTP_HOST='school.test', enforce_csrf_checks=True)
        self.assertEqual(self.post(BASE + 'conversations/', {}, client=visitor).status_code, 403)
        self.assertEqual(visitor.get('/seller/ai/').status_code, 200)
        token = visitor.cookies[settings.CSRF_COOKIE_NAME].value
        response = visitor.post(BASE + 'conversations/', {}, content_type='application/json',
                                HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 201, response.content)

    def test_host_status_explains_shared_catalogue_and_fails_closed_on_bad_account(self):
        self.assertTrue(self.client.get(BASE + 'status/').json()['shared_demo'])
        self.assertIn('No login', self.client.get(BASE + 'me/').json()['onboarding'])
        actor = get_user_model().objects.get(email=settings.SELLER_SHARED_DEMO_EMAIL)
        actor.is_admin = True
        actor.save(update_fields=['is_admin'])
        self.assertEqual(self.client.get(BASE + 'snapshot/').status_code, 503)
