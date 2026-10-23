import json
import uuid
from datetime import timedelta
from unittest.mock import patch, Mock

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from products.models import Maker, Category, Product, ProductVariant
from orders.models import Order, Cart, PaymentStatus, SellerFulfillment
from payments.models import Payment
from .models import Conversation, OrderDraft, Message, Event
from . import assistant


@override_settings(DEBUG=True, CONCIERGE_DEMO=True, DEEPSEEK_API_KEY="",
                   PAYMENT_BACKEND="payments.services.MockPaymentProvider")
class ConciergeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = get_user_model().objects.create_user(email="seller@test.local", password="password", is_seller=True)
        cls.other = get_user_model().objects.create_user(email="other@test.local", password="password", is_seller=True)
        cls.maker = Maker.objects.create(name="Studio", slug="studio", owner=cls.seller)
        cls.other_maker = Maker.objects.create(name="Other", slug="other", owner=cls.other)
        cls.category = Category.objects.create(name="Ceramics", slug="ceramics")
        cls.product = Product.objects.create(name="Blue Bowl", slug="blue-bowl", maker=cls.maker,
            category=cls.category, price="25.00", stock_quantity=10)
        cls.variant_product = Product.objects.create(name="Cup", slug="cup", maker=cls.maker,
            category=cls.category, price="15.00", stock_quantity=0)
        cls.variant = ProductVariant.objects.create(product=cls.variant_product, label="Blue", sku="CUP-BLUE", stock_quantity=5)
        cls.foreign = Product.objects.create(name="Foreign", slug="foreign", maker=cls.other_maker,
            category=cls.category, price="99.00", stock_quantity=10)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.seller)
        self.conversation = Conversation.objects.create(maker=self.maker, created_by=self.seller)
        self.base = f"/seller/assistant/conversations/{self.conversation.uuid}/"

    def payload(self, **kwargs):
        result = {"request_id": str(uuid.uuid4()), "lines": [{"product": "blue-bowl", "quantity": 2}],
            "email": "buyer@example.test", "phone": "13800000000",
            "shipping_address": {"first_name": "禾", "last_name": "陈", "address_line_1": "演示路 100 号",
                                 "city": "上海", "postal_code": "200000"}}
        result.update(kwargs)
        return result

    def draft(self, **kwargs):
        response = self.client.post(self.base+"drafts/", self.payload(**kwargs), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def action(self, draft, action, **kwargs):
        return self.client.post(f"/seller/assistant/drafts/{draft['id']}/action/",
            {"action": action, **kwargs}, format="json")

    def paid(self):
        d = self.draft()
        self.assertEqual(self.action(d,"confirm",confirmed=True).status_code,200)
        self.assertEqual(self.action(d,"pay").status_code,200)
        return d

    def test_complete_flow_and_each_action_is_idempotent(self):
        d = self.draft()
        self.assertEqual(Order.objects.count(),0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,10)
        self.assertEqual(d["total"],"58.00")
        for action, args in [("confirm",{"confirmed":True}),("pay",{}),("pack",{}),("packed",{}),
                             ("ship",{"carrier":"Demo","tracking_number":"DEMO123456"})]:
            for _ in range(2):
                response = self.action(d,action,**args)
                self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(Order.objects.count(),1)
        self.assertEqual(Payment.objects.count(),1)
        self.assertEqual(Event.objects.count(),6)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,8)
        order=Order.objects.get()
        self.assertIsNone(order.user_id)
        self.assertEqual(order.customer_email,"buyer@example.test")
        self.assertEqual(order.payment_status,PaymentStatus.PAID)
        self.assertEqual(order.status,"shipped")
        self.assertEqual(SellerFulfillment.objects.get().tracking_number,"DEMO123456")

    def test_customer_cannot_use_desk_api(self):
        buyer=get_user_model().objects.create_user(email="buyer@test.local",password="password")
        self.client.force_authenticate(buyer)
        self.assertEqual(self.client.get("/seller/assistant/conversations/").status_code,403)

    def test_anonymous_cannot_use_api(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get("/seller/assistant/conversations/").status_code,(401,403))

    def test_cross_seller_read_and_action_hidden(self):
        d=self.draft()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.base).status_code,404)
        self.assertEqual(self.action(d,"confirm",confirmed=True).status_code,404)
        self.assertEqual(self.client.post(self.base+"messages/",{"request_id":str(uuid.uuid4()),"text":"hello"},format="json").status_code,404)

    def test_foreign_product_rejected(self):
        r=self.client.post(self.base+"drafts/",self.payload(lines=[{"product":"foreign","quantity":1}]),format="json")
        self.assertEqual(r.status_code,400)
        self.assertFalse(Cart.objects.exists())

    def test_catalog_scoped_to_seller(self):
        response=self.client.get("/seller/assistant/conversations/")
        self.assertEqual({p["product"] for p in response.data["catalog"]},{"blue-bowl","cup"})

    def test_expired_draft_rejected(self):
        d=self.draft()
        OrderDraft.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.action(d,"confirm",confirmed=True).status_code,400)
        self.assertFalse(Order.objects.exists())

    def test_price_change_requires_new_confirmation(self):
        d=self.draft()
        Product.objects.filter(pk=self.product.pk).update(price="30.00")
        self.assertEqual(self.action(d,"confirm",confirmed=True).status_code,400)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Cart.objects.exists())

    def test_shipping_change_requires_new_confirmation(self):
        d=self.draft()
        from django.conf import settings
        with override_settings(COMMERCE={**settings.COMMERCE,"SHIPPING_STANDARD":"9"}):
            self.assertEqual(self.action(d,"confirm",confirmed=True).status_code,400)

    def test_stock_change_rejected(self):
        d=self.draft()
        Product.objects.filter(pk=self.product.pk).update(stock_quantity=1)
        self.assertEqual(self.action(d,"confirm",confirmed=True).status_code,400)
        self.assertFalse(Order.objects.exists())

    def test_delisted_product_rejected(self):
        d=self.draft()
        Product.objects.filter(pk=self.product.pk).update(is_active=False)
        self.assertEqual(self.action(d,"confirm",confirmed=True).status_code,400)

    def test_variant_required_and_revalidated(self):
        r=self.client.post(self.base+"drafts/",self.payload(lines=[{"product":"cup","quantity":1}]),format="json")
        self.assertEqual(r.status_code,400)
        d=self.draft(lines=[{"product":"cup","variant":str(self.variant.uuid),"quantity":2}])
        ProductVariant.objects.filter(pk=self.variant.pk).update(is_active=False)
        self.assertEqual(self.action(d,"confirm",confirmed=True).status_code,400)

    def test_wrong_variant_rejected(self):
        r=self.client.post(self.base+"drafts/",self.payload(lines=[{"product":"blue-bowl","variant":str(self.variant.uuid),"quantity":1}]),format="json")
        self.assertEqual(r.status_code,400)

    def test_confirmation_must_be_explicit(self):
        d=self.draft()
        self.assertEqual(self.action(d,"confirm").status_code,400)
        self.assertFalse(Order.objects.exists())

    def test_payment_and_packing_order_enforced(self):
        d=self.draft()
        self.assertEqual(self.action(d,"pay").status_code,400)
        self.action(d,"confirm",confirmed=True)
        self.assertEqual(self.action(d,"pack").status_code,400)
        self.assertEqual(self.action(d,"ship",carrier="Demo",tracking_number="DEMO123456").status_code,400)
        self.action(d,"pay")
        self.assertEqual(self.action(d,"packed").status_code,400)
        self.action(d,"pack")
        self.assertEqual(self.action(d,"ship",carrier="Demo",tracking_number="DEMO123456").status_code,400)

    def test_tracking_required(self):
        d=self.paid()
        self.action(d,"pack");self.action(d,"packed")
        self.assertEqual(self.action(d,"ship").status_code,400)
        self.assertEqual(self.action(d,"ship",carrier="Demo",tracking_number="?").status_code,400)

    def test_duplicate_draft_request_returns_same_draft(self):
        payload=self.payload()
        a=self.client.post(self.base+"drafts/",payload,format="json")
        b=self.client.post(self.base+"drafts/",payload,format="json")
        self.assertEqual(a.data["id"],b.data["id"])
        self.assertEqual(OrderDraft.objects.count(),1)

    def test_message_deduplicated_and_does_not_create_order(self):
        payload={"request_id":str(uuid.uuid4()),"text":"买2个 Blue Bowl"}
        a=self.client.post(self.base+"messages/",payload,format="json")
        b=self.client.post(self.base+"messages/",payload,format="json")
        self.assertEqual(a.data,b.data)
        self.assertEqual(a.data["engine"],"offline")
        self.assertEqual(a.data["lines"][0]["quantity"],2)
        self.assertEqual(Message.objects.count(),1)
        self.assertFalse(Order.objects.exists())

    def test_invalid_quantities_and_duplicates_rejected(self):
        for qty in [0,-1,100,1.5,"oops"]:
            r=self.client.post(self.base+"drafts/",self.payload(lines=[{"product":"blue-bowl","quantity":qty}]),format="json")
            self.assertEqual(r.status_code,400)
        r=self.client.post(self.base+"drafts/",self.payload(lines=[{"product":"blue-bowl","quantity":1}]*2),format="json")
        self.assertEqual(r.status_code,400)

    @override_settings(DEBUG=False)
    def test_disabled_outside_debug(self):
        # Secure redirect occurs before the view in production.
        response=self.client.get("/seller/assistant/conversations/",secure=True)
        self.assertEqual(response.status_code,403)

    @override_settings(CONCIERGE_DEMO=False)
    def test_disabled_without_opt_in(self):
        self.assertEqual(self.client.get("/seller/assistant/conversations/").status_code,403)

    @override_settings(PAYMENT_BACKEND="payments.services.StripeWeChatProvider")
    def test_real_provider_cannot_be_used(self):
        self.assertEqual(self.client.get("/seller/assistant/conversations/").status_code,403)

    def test_csrf_enforced_for_sessions(self):
        client=APIClient(enforce_csrf_checks=True)
        client.force_login(self.seller)
        self.assertEqual(client.post("/seller/assistant/conversations/",{},format="json").status_code,403)

    @override_settings(DEEPSEEK_API_KEY="fake-test-key")
    @patch("concierge.assistant.requests.post")
    def test_unknown_ai_sku_falls_back_safely(self, post):
        response=Mock()
        response.json.return_value={"choices":[{"message":{"content":json.dumps({"reply":"buy this","lines":[{"product":"foreign","quantity":1}]})}}]}
        post.return_value=response
        result=assistant.suggest("Blue Bowl",[{"product":"blue-bowl","name":"Blue Bowl","variants":[]}])
        self.assertEqual(result["engine"],"offline")
        self.assertEqual(result["lines"][0]["product"],"blue-bowl")

    @override_settings(DEEPSEEK_API_KEY="fake-test-key")
    @patch("concierge.assistant.requests.post")
    def test_valid_ai_suggestion_is_parsed(self, post):
        response=Mock()
        response.json.return_value={"choices":[{"message":{"content":json.dumps({"reply":"请核对","lines":[{"product":"blue-bowl","quantity":2}]})}}]}
        post.return_value=response
        result=assistant.suggest("two bowls",[{"product":"blue-bowl","name":"Blue Bowl","variants":[]}])
        self.assertEqual(result["engine"],"deepseek")
        self.assertEqual(result["lines"][0]["quantity"],2)

    @override_settings(DEEPSEEK_API_KEY="fake-test-key")
    @patch("concierge.assistant.requests.post")
    def test_malformed_ai_response_falls_back(self, post):
        response=Mock()
        response.json.return_value={"choices":[{"message":{"content":"not json"}}]}
        post.return_value=response
        self.assertEqual(assistant.suggest("hello",[])["engine"],"offline")


@override_settings(DEBUG=True, CONCIERGE_DEMO=True, DEEPSEEK_API_KEY="",
                   PAYMENT_BACKEND="payments.services.MockPaymentProvider")
class ConcurrentConfirmationTests(TransactionTestCase):
    """Use independent PostgreSQL connections, not a mocked stock counter."""
    def setUp(self):
        from .serializers import DraftInput
        from .services import make_draft
        self.seller=get_user_model().objects.create_user(email="concurrent@test.local",is_seller=True)
        maker=Maker.objects.create(name="Concurrent",slug="concurrent",owner=self.seller)
        category=Category.objects.create(name="Test",slug="test")
        self.product=Product.objects.create(name="Last Bowl",slug="last-bowl",maker=maker,
            category=category,price="25.00",stock_quantity=1)
        self.drafts=[]
        for _ in range(2):
            c=Conversation.objects.create(maker=maker,created_by=self.seller)
            payload={"request_id":str(uuid.uuid4()),"lines":[{"product":"last-bowl","quantity":1}],
                "email":"buyer@example.test","shipping_address":{"first_name":"A","last_name":"B",
                "address_line_1":"Test address","city":"Test","postal_code":"12345"}}
            serializer=DraftInput(data=payload)
            serializer.is_valid(raise_exception=True)
            self.drafts.append(make_draft(self.seller,c.uuid,serializer.validated_data))

    def race(self, ids):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections, connection
        from rest_framework.exceptions import ValidationError
        from .services import act
        barrier=Barrier(2)
        actor_id=self.seller.pk
        def confirm(draft_id):
            try:
                actor=get_user_model().objects.get(pk=actor_id)
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                barrier.wait(timeout=10)
                result=act(actor,draft_id,{"action":"confirm","confirmed":True})
                return result.order_id
            except ValidationError:
                return None
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(confirm,i) for i in ids]
            return [f.result(timeout=20) for f in futures]

    def test_racing_buyers_cannot_oversell_last_piece(self):
        results=self.race([d.uuid for d in self.drafts])
        self.assertEqual(sum(r is not None for r in results),1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,0)
        self.assertEqual(Order.objects.count(),1)

    def test_racing_retries_create_only_one_order(self):
        results=self.race([self.drafts[0].uuid]*2)
        self.assertIsNotNone(results[0])
        self.assertEqual(results[0],results[1])
        self.assertEqual(Order.objects.count(),1)
        self.assertEqual(Payment.objects.count(),1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,0)
