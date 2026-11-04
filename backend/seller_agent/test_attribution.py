from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from accounts.demo import DEMO_SELLER, DEMO_SELLER_NAME
from orders.models import OrderStatus, PaymentStatus
from orders.services import create_seller_fulfillments
from orders.tests.factories import make_bare_order, make_buyer, make_category, make_maker, make_order_item, make_product, make_seller_user
from products.models import Product
from .models import SellerOperation

BASE = '/api/seller-agent/v1/'


@override_settings(
    SELLER_SHARED_DEMO_ENABLED=False, SELLER_SHARED_DEMO_HOSTS=['school.test'],
    ALLOWED_HOSTS=['school.test', 'testserver'], SELLER_AGENT_ENABLED=True,
    SELLER_AGENT_USE_LLM=False, SELLER_AGENT_API_KEY='', SECURE_SSL_REDIRECT=False,
    STORAGES={**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
)
class SellerAttributionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = make_seller_user(DEMO_SELLER['email'], first_name='chen')
        cls.seller.last_name = 'mei lin'
        cls.seller.save()
        cls.maker = make_maker('chen-meilin', DEMO_SELLER_NAME, owner=cls.seller)
        cls.other_maker = make_maker('other-artisan', 'Other artisan')
        cls.category = make_category('ceramics', 'Ceramics')
        cls.product = make_product(maker=cls.other_maker, category=cls.category, slug='existing-artisan-cup')
        cls.buyer = make_buyer('attribution-buyer@example.test')
        cls.order = make_bare_order(payment_status=PaymentStatus.PAID, status=OrderStatus.CONFIRMED)
        cls.order.user = cls.buyer
        cls.order.save()
        make_order_item(order=cls.order, product=cls.product)
        cls.parcel = create_seller_fulfillments(cls.order)[0]

    def setUp(self):
        self.client = Client(HTTP_HOST='school.test', HTTP_USER_AGENT='AtelierSeller/1.4.0', HTTP_ACCEPT_LANGUAGE='zh-hans')
        self.client.force_login(self.seller)
        self.conversation = self.post('conversations/', {}).json()['id']

    def post(self, path, payload, client=None):
        return (client or self.client).post(BASE + path, payload, content_type='application/json')

    def prepare(self, action, values, target='', client=None, conversation=None):
        response = self.post(f'conversations/{conversation or self.conversation}/changes/',
            {'request_id': str(uuid4()), 'action': action, 'target': target, 'values': values}, client)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def confirm(self, change, client=None):
        response = self.post(f"changes/{change['id']}/confirm/", {'confirmed': True}, client)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def listing(self):
        return {'name': 'Attribution demo cup', 'category': 'ceramics', 'description': 'Test cup', 'price': '23.00', 'quantity': 8}

    def test_new_product_belongs_to_authenticated_seller_and_audit_is_idempotent(self):
        change = self.prepare('listing', self.listing())
        self.assertFalse(SellerOperation.objects.exists())
        confirmed = self.confirm(change)
        self.assertEqual(confirmed['operation']['actor_name'], DEMO_SELLER_NAME)
        product = Product.objects.get(slug=confirmed['result']['product'])
        self.assertEqual(product.maker_id, self.maker.pk)
        self.assertFalse(product.is_active)
        self.confirm(change)
        self.assertEqual(SellerOperation.objects.count(), 1)
        self.assertEqual(SellerOperation.objects.get().actor_id, self.seller.pk)
        self.assertNotIn('seller@', str(confirmed['operation']))

    def test_edit_preserves_existing_maker_and_is_visible_to_another_client(self):
        self.confirm(self.prepare('stock', {'quantity': 17}, self.product.slug))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 17)
        self.assertEqual(self.product.maker_id, self.other_maker.pk)
        peer = Client(HTTP_HOST='school.test', HTTP_ACCEPT_LANGUAGE='zh-hans')
        row = next(p for p in peer.get(BASE + 'snapshot/').json()['products'] if p['slug'] == self.product.slug)
        self.assertEqual(row['last_operation']['actor_name'], DEMO_SELLER_NAME)
        self.assertEqual(row['seller_name'], self.other_maker.name)
        self.assertContains(peer.get(f'/products/{self.product.slug}/'), '最近操作人')
        self.assertEqual(peer.get(f'/api/products/{self.product.slug}/').json()['last_operation']['actor_name'], DEMO_SELLER_NAME)

    def test_shipment_and_delivery_record_actor_and_buyer_sees_name(self):
        self.confirm(self.prepare('fulfillment', {'carrier': 'Demo carrier', 'tracking_number': 'TEST-ATR-1'}, str(self.parcel.uuid)))
        self.confirm(self.prepare('delivery', {}, str(self.parcel.uuid)))
        self.assertEqual(SellerOperation.objects.filter(order=self.order, actor=self.seller).count(), 2)
        row = Client(HTTP_HOST='school.test').get(BASE + 'snapshot/').json()['orders'][0]
        self.assertEqual(row['last_operation']['actor_name'], DEMO_SELLER_NAME)
        buyer = Client(HTTP_HOST='testserver', HTTP_ACCEPT_LANGUAGE='zh-hans')
        buyer.force_login(self.buyer)
        self.assertContains(buyer.get(f'/account/orders/{self.order.order_number}/'), DEMO_SELLER_NAME)
        self.assertEqual(buyer.get(f'/api/orders/{self.order.uuid}/').json()['last_operation']['actor_name'], DEMO_SELLER_NAME)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.DELIVERED)

    def test_anonymous_changes_are_not_attributed_to_chen(self):
        visitor = Client(HTTP_HOST='school.test')
        conversation = self.post('conversations/', {}, visitor).json()['id']
        change = self.prepare('listing', self.listing(), client=visitor, conversation=conversation)
        result = self.confirm(change, visitor)
        self.assertNotEqual(result['operation']['actor_name'], DEMO_SELLER_NAME)
        self.assertNotEqual(Product.objects.get(slug=result['result']['product']).maker_id, self.maker.pk)

    def test_buyer_session_is_not_mislabelled_as_demo_seller(self):
        visitor = Client(HTTP_HOST='school.test')
        visitor.force_login(self.buyer)
        conversation = self.post('conversations/', {}, visitor).json()['id']
        result = self.confirm(self.prepare('stock', {'quantity': 16}, self.product.slug,
                                          client=visitor, conversation=conversation), visitor)
        self.assertNotEqual(result['operation']['actor_name'], DEMO_SELLER_NAME)

    def test_switching_actor_requires_new_listing_preview(self):
        change = self.prepare('listing', self.listing())
        self.client.logout()
        response = self.post(f"changes/{change['id']}/confirm/", {'confirmed': True})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(SellerOperation.objects.exists())

    def test_failing_audit_rolls_back_the_product_change(self):
        change = self.prepare('stock', {'quantity': 5}, self.product.slug)
        with patch('seller_agent.services.record_operation', side_effect=RuntimeError('test audit failure')):
            response = self.post(f"changes/{change['id']}/confirm/", {'confirmed': True})
            self.assertEqual(response.status_code, 500)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 50)
        self.assertFalse(SellerOperation.objects.exists())

    def test_product_editor_uses_real_owner_and_logs_edits(self):
        payload = {'name': 'Form attribution cup', 'category': self.category.pk, 'price': '21.00',
            'stock_quantity': '9', 'is_active': 'on', 'product_variants-TOTAL_FORMS': '0',
            'product_variants-INITIAL_FORMS': '0', 'product_images-TOTAL_FORMS': '0', 'product_images-INITIAL_FORMS': '0'}
        created = self.client.post('/seller/products/add/', payload)
        self.assertEqual(created.status_code, 302, created.content)
        product = Product.objects.get(name=payload['name'])
        self.assertEqual(product.maker_id, self.maker.pk)
        self.assertEqual(product.seller_operations.get().actor_id, self.seller.pk)
        payload['name'] = 'Edited attribution cup'
        edited = self.client.post(f'/seller/products/{self.product.slug}/edit/', payload)
        self.assertEqual(edited.status_code, 302, edited.content)
        self.assertEqual(self.product.seller_operations.get().actor_id, self.seller.pk)
        self.product.refresh_from_db()
        self.assertEqual(self.product.maker_id, self.other_maker.pk)

    def test_product_api_uses_real_owner_and_cannot_choose_an_actor(self):
        response = self.client.post('/api/seller/products/', {'name': 'API attribution cup',
            'slug': 'api-attribution-cup', 'description': 'Test cup', 'price': '22.00',
            'category': self.category.pk, 'stock_quantity': 8}, content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        product = Product.objects.get(slug='api-attribution-cup')
        self.assertEqual(product.maker_id, self.maker.pk)
        updated = self.client.patch(f'/api/seller/products/{product.slug}/',
            {'stock_quantity': 9, 'actor': self.buyer.pk}, content_type='application/json')
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(product.seller_operations.count(), 2)
        self.assertEqual(set(product.seller_operations.values_list('actor_id', flat=True)), {self.seller.pk})

    def test_actor_name_snapshot_survives_profile_rename(self):
        self.confirm(self.prepare('stock', {'quantity': 7}, self.product.slug))
        get_user_model().objects.filter(pk=self.seller.pk).update(first_name='Later', last_name='Name')
        self.assertEqual(SellerOperation.objects.get().actor_name, DEMO_SELLER_NAME)

    def test_deleted_product_keeps_operator_and_product_identifier(self):
        response = self.client.delete(f'/api/seller/products/{self.product.slug}/')
        self.assertEqual(response.status_code, 204, response.content)
        operation = SellerOperation.objects.get()
        self.assertEqual(operation.actor_id, self.seller.pk)
        self.assertEqual(operation.product_slug, 'existing-artisan-cup')
        self.assertEqual(operation.action, 'product_delete')
        self.assertIsNone(operation.product_id)
