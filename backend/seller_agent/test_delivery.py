from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from orders.models import FulfillmentStatus, Order, OrderStatus, PaymentStatus
from orders.services import create_seller_fulfillments
from orders.tests.factories import make_bare_order, make_buyer, make_category, make_maker, make_order_item, make_product, make_seller_user
from . import planner

BASE = '/api/seller-agent/v1/'


@override_settings(
    SELLER_SHARED_DEMO_ENABLED=False, SELLER_SHARED_DEMO_HOSTS=['school.test'],
    ALLOWED_HOSTS=['school.test', 'testserver'], SELLER_AGENT_ENABLED=True,
    SELLER_AGENT_USE_LLM=False, SELLER_AGENT_API_KEY='', SECURE_SSL_REDIRECT=False,
    STORAGES={**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
)
class SellerDeliveryTests(TestCase):
    def setUp(self):
        self.seller = make_seller_user('delivery-seller@example.test')
        self.maker = make_maker('delivery-studio', 'Delivery Studio', owner=self.seller)
        self.product = make_product(maker=self.maker, category=make_category(), slug='delivery-cup')
        self.buyer = make_buyer('delivery-buyer@example.test')
        self.order = make_bare_order(payment_status=PaymentStatus.PAID, status=OrderStatus.CONFIRMED)
        self.order.user = self.buyer
        self.order.save()
        make_order_item(order=self.order, product=self.product)
        self.parcel = create_seller_fulfillments(self.order)[0]
        self.parcel.status = FulfillmentStatus.FULFILLED
        self.parcel.shipped_at = timezone.now()
        self.parcel.save()
        self.client = Client(HTTP_HOST='school.test', HTTP_ACCEPT_LANGUAGE='zh-hans')
        self.conversation = self.post('conversations/', {}).json()['id']

    def post(self, path, data, client=None):
        return (client or self.client).post(BASE + path, data, content_type='application/json')

    def prepare(self, client=None, conversation=None, values=None):
        return self.post(f'conversations/{conversation or self.conversation}/changes/',
            {'request_id': str(uuid4()), 'action': 'delivery', 'target': str(self.parcel.uuid),
             'values': values or {}}, client)

    def test_preview_requires_confirmation_and_updates_buyer_on_confirm(self):
        snapshot = self.client.get(BASE + 'snapshot/').json()['orders'][0]
        self.assertTrue(snapshot['can_deliver'])
        preview = self.prepare()
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertIn('已发货', preview.json()['summary'])
        self.assertIn('已送达', preview.json()['summary'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.CONFIRMED)
        path = f"changes/{preview.json()['id']}/confirm/"
        self.assertEqual(self.post(path, {'confirmed': False}).status_code, 400)
        with patch('content.services.send_order_delivered') as notify:
            with self.captureOnCommitCallbacks(execute=True):
                confirmed = self.post(path, {'confirmed': True})
                again = self.post(path, {'confirmed': True})
            self.assertEqual(confirmed.status_code, 200, confirmed.content)
            self.assertEqual(again.status_code, 200)
            notify.assert_called_once()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.DELIVERED)
        buyer = Client(HTTP_HOST='testserver')
        buyer.force_login(self.buyer)
        self.assertEqual(buyer.get(f'/api/orders/{self.order.uuid}/').json()['status'], 'delivered')
        row = self.client.get(BASE + 'snapshot/').json()['orders'][0]
        self.assertFalse(row['can_deliver'])
        self.assertEqual(row['status'], 'delivered')

    def test_rejects_unshipped_and_unpaid_orders(self):
        self.parcel.status = FulfillmentStatus.UNFULFILLED
        self.parcel.save()
        self.assertEqual(self.prepare().status_code, 400)
        self.parcel.status = FulfillmentStatus.FULFILLED
        self.parcel.save()
        self.order.payment_status = PaymentStatus.UNPAID
        self.order.save()
        self.assertEqual(self.prepare().status_code, 400)

    def test_cancellation_after_preview_prevents_delivery(self):
        preview = self.prepare().json()
        Order.objects.filter(pk=self.order.pk).update(status=OrderStatus.CANCELLED)
        self.assertEqual(self.post(f"changes/{preview['id']}/confirm/", {'confirmed': True}).status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.CANCELLED)

    def test_cannot_complete_a_different_makers_parcel(self):
        other_maker = make_maker('other-delivery-studio', 'Other Delivery Studio')
        other = make_product(maker=other_maker, category=self.product.category, slug='other-delivery-cup')
        make_order_item(order=self.order, product=other)
        create_seller_fulfillments(self.order)
        rows = self.client.get(BASE + 'snapshot/').json()['orders']
        self.assertTrue(all(not row['can_deliver'] for row in rows))
        self.assertEqual(self.prepare().status_code, 400)

    def test_normal_seller_cannot_deliver_another_sellers_order(self):
        user = make_seller_user('unrelated-delivery@example.test')
        make_maker('unrelated-delivery-studio', 'Unrelated Studio', owner=user)
        client = Client(HTTP_HOST='testserver')
        client.force_login(user)
        conversation = self.post('conversations/', {}, client).json()['id']
        response = self.prepare(client, conversation)
        self.assertIn(response.status_code, (400, 404))

    def test_verified_seller_can_confirm_own_delivered_order(self):
        client = Client(HTTP_HOST='testserver')
        client.force_login(self.seller)
        conversation = self.post('conversations/', {}, client).json()['id']
        preview = self.post(f'conversations/{conversation}/changes/', {
            'request_id': str(uuid4()), 'action': 'delivery',
            'target': str(self.order.uuid), 'values': {}}, client)
        self.assertEqual(preview.status_code, 200, preview.content)
        confirmed = self.post(f"changes/{preview.json()['id']}/confirm/", {'confirmed': True}, client)
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.DELIVERED)

    def test_exact_chinese_chat_command_prepares_delivery_without_executing(self):
        response = self.post(f'conversations/{self.conversation}/messages/',
            {'request_id': str(uuid4()), 'text': f'确认送达 {self.parcel.uuid}'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['change']['action'], 'delivery')
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, OrderStatus.DELIVERED)

    def test_model_plan_rejects_unauthorized_fields_and_ineligible_delivery(self):
        orders = [{'uuid': str(self.parcel.uuid), 'can_deliver': True}]
        result = planner._validated({'intent': 'delivery', 'target': str(self.parcel.uuid), 'values': {}}, [], orders, [], {})
        self.assertEqual(result['intent'], 'delivery')
        with self.assertRaises(ValueError):
            planner._validated({'intent': 'delivery', 'target': str(self.parcel.uuid),
                                'values': {'payment_status': 'paid'}}, [], orders, [], {})
        with self.assertRaises(ValueError):
            planner._validated({'intent': 'delivery', 'target': str(self.parcel.uuid),
                                'values': {}}, [], [{'uuid': str(self.parcel.uuid), 'can_deliver': False}], [], {})
