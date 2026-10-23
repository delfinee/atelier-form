"""Test the boundary between the seller workspace and paired customer clients."""
from datetime import timedelta
from uuid import uuid4
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from products.models import Maker, Category, Product
from orders.models import Order
from concierge.models import Conversation, OrderDraft, Event
from concierge.test_public_demo import middleware, templates
from .models import CustomerSession, SellerReply, CustomerAction
from .auth import digest


@override_settings(DEBUG=True, CONCIERGE_DEMO=True, PUBLIC_CONCIERGE_DEMO=True,
    DEEPSEEK_API_KEY="", PAYMENT_BACKEND="payments.services.MockPaymentProvider")
class WorkbenchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = get_user_model().objects.create_user(email="seller@test.invalid", is_seller=True)
        cls.other = get_user_model().objects.create_user(email="other@test.invalid", is_seller=True)
        cls.maker = Maker.objects.create(owner=cls.seller, name="Studio", slug="studio")
        cls.other_maker = Maker.objects.create(owner=cls.other, name="Other", slug="other")
        category = Category.objects.create(name="Bowls", slug="bowls")
        cls.product = Product.objects.create(maker=cls.maker, category=category, name="Blue bowl",
                                            slug="blue-bowl", price="25.00", stock_quantity=10)

    def setUp(self):
        cache.clear()
        self.s = APIClient()
        self.s.force_authenticate(self.seller)
        self.base = "/seller/workbench/api/"
        self.invitation = self.s.post(self.base + "invitations/", {"label": "Alex"}, format="json").data
        self.c = APIClient()
        self.token = self.invitation["preview_url"].split("#token=")[1]
        self.c.credentials(HTTP_AUTHORIZATION="Customer " + self.token)
        self.conversation = self.invitation["conversation_id"]
        self.customer = "/api/mini-store/v1/"

    def quote(self):
        payload = {"request_id": str(uuid4()), "lines": [{"product": "blue-bowl", "quantity": 2}],
                   "email": "alex@example.test", "shipping_address": {"first_name": "Alex",
                   "last_name": "Chen", "address_line_1": "100 Demo Road", "city": "Shanghai",
                   "postal_code": "200000"}}
        r = self.s.post(self.base + f"conversations/{self.conversation}/quote/", payload, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        return r.data

    def action(self, draft, action, **extra):
        return self.s.post(self.base + f"drafts/{draft['id']}/action/", {"action": action, **extra}, format="json")

    def test_customer_to_seller_round_trip_through_shipment(self):
        payload = {"request_id": str(uuid4()), "text": "Blue bowl x2"}
        for _ in range(2):
            r = self.c.post(self.customer + "messages/", payload, format="json")
            self.assertEqual(r.status_code, 200, r.data)
        overview = self.s.get(self.base + "overview/").data
        self.assertEqual(overview["needs_reply"], 1)
        self.assertEqual(overview["conversations"][0]["channel"], "Mini Program preview")
        reply = {"request_id": str(uuid4()), "text": "Yes, I can prepare your quote."}
        for _ in range(2):
            self.assertEqual(self.s.post(self.base + f"conversations/{self.conversation}/reply/", reply, format="json").status_code, 200)
        self.assertEqual(SellerReply.objects.count(), 1)
        self.assertEqual(self.s.get(self.base + "overview/").data["needs_reply"], 0)
        state = self.c.get(self.customer + "conversation/").data
        self.assertEqual([m["role"] for m in state["messages"]], ["customer", "assistant", "seller"])
        d = self.quote()
        self.assertEqual(d["stage"], "review")
        self.assertEqual(self.c.get(self.customer + "conversation/").data["drafts"][0]["id"], d["id"])
        for route in ("confirm", "demo-payment"):
            for _ in range(2):
                r = self.c.post(self.customer + f"quotes/{d['id']}/{route}/", {"confirmed": True}, format="json")
                self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(CustomerAction.objects.count(), 2)
        self.assertEqual(r.data["stage"], "packing")
        self.assertEqual([e["initiator"] for e in r.data["events"]], ["seller", "customer", "customer"])
        for action in ("pack", "packed", "ship"):
            r = self.action(d, action, carrier="Demo Express", tracking_number="DEMO-123456")
            self.assertEqual(r.status_code, 200, r.data)
        customer = self.c.get(self.customer + "conversation/").data
        self.assertEqual(customer["drafts"][0]["stage"], "shipped")
        self.assertEqual(customer["drafts"][0]["order"]["tracking_number"], "DEMO-123456")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)

    def test_customer_cannot_act_as_seller_or_choose_other_conversation(self):
        d = self.quote()
        for path in ("overview/", "conversations/" + self.conversation + "/"):
            self.assertIn(self.c.get(self.base + path).status_code, (401, 403))
        self.assertIn(self.c.post(self.base + f"drafts/{d['id']}/action/", {"action": "pay"}, format="json").status_code, (401, 403))
        self.assertIn(self.c.get("/seller/assistant/conversations/").status_code, (401, 403))
        second = self.s.post(self.base + "invitations/", {"label": "Other buyer"}, format="json").data
        self.c.credentials(HTTP_AUTHORIZATION="Customer " + second["preview_url"].split("#token=")[1])
        self.assertFalse(self.c.get(self.customer + "conversation/").data["drafts"])
        for route in ("confirm", "demo-payment"):
            self.assertEqual(self.c.post(self.customer + f"quotes/{d['id']}/{route}/", {"confirmed": True}, format="json").status_code, 404)
        self.assertFalse(Order.objects.exists())

    def test_other_seller_sees_no_data_and_cannot_reply_quote_or_fulfill(self):
        d = self.quote()
        self.s.force_authenticate(self.other)
        overview = self.s.get(self.base + "overview/").data
        self.assertFalse(overview["conversations"])
        self.assertFalse(overview["drafts"])
        self.assertFalse(overview["catalog"])
        self.assertEqual(self.s.get(self.base + f"conversations/{self.conversation}/").status_code, 404)
        self.assertEqual(self.s.post(self.base + f"conversations/{self.conversation}/reply/", {"text": "Hi", "request_id": str(uuid4())}, format="json").status_code, 404)
        self.assertEqual(self.action(d, "confirm", confirmed=True).status_code, 404)

    def test_customer_must_confirm_and_cannot_pay_before_order_or_pack(self):
        d = self.quote()
        self.assertEqual(self.c.post(self.customer + f"quotes/{d['id']}/confirm/", {}, format="json").status_code, 400)
        self.assertEqual(self.c.post(self.customer + f"quotes/{d['id']}/confirm/", {"confirmed": "false"}, format="json").status_code, 400)
        self.assertEqual(self.c.post(self.customer + f"quotes/{d['id']}/demo-payment/", {}, format="json").status_code, 400)
        self.assertEqual(self.c.post(self.customer + f"quotes/{d['id']}/pack/", {}, format="json").status_code, 404)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(CustomerAction.objects.exists())

    def test_price_stock_and_expiry_are_rechecked(self):
        d = self.quote()
        Product.objects.filter(pk=self.product.pk).update(price="30.00")
        endpoint = self.customer + f"quotes/{d['id']}/confirm/"
        self.assertEqual(self.c.post(endpoint, {"confirmed": True}, format="json").status_code, 400)
        Product.objects.filter(pk=self.product.pk).update(price="25.00", stock_quantity=1)
        self.assertEqual(self.c.post(endpoint, {"confirmed": True}, format="json").status_code, 400)
        Product.objects.filter(pk=self.product.pk).update(stock_quantity=10)
        OrderDraft.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.c.post(endpoint, {"confirmed": True}, format="json").status_code, 400)
        self.assertEqual(self.s.get(self.base + "overview/").data["counts"]["expired"], 1)
        self.assertFalse(Order.objects.exists())

    def test_invitation_is_hashed_expires_and_can_be_revoked(self):
        access = CustomerSession.objects.get()
        self.assertEqual(access.token_hash, digest(self.token))
        self.assertNotEqual(access.token_hash, self.token)
        CustomerSession.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.c.get(self.customer + "conversation/").status_code, 401)
        CustomerSession.objects.update(expires_at=timezone.now()+timedelta(hours=1))
        self.assertEqual(self.c.get(self.customer + "conversation/").status_code, 200)
        self.assertEqual(self.s.post(self.base + f"conversations/{self.conversation}/revoke/", {}, format="json").status_code, 200)
        self.assertEqual(self.c.get(self.customer + "conversation/").status_code, 401)

    def test_disabled_maker_and_real_payment_provider_block_customer(self):
        Maker.objects.filter(pk=self.maker.pk).update(is_active=False)
        self.assertEqual(self.c.get(self.customer + "conversation/").status_code, 401)
        self.assertEqual(self.s.get(self.base + "overview/").status_code, 403)
        Maker.objects.filter(pk=self.maker.pk).update(is_active=True)
        with override_settings(PAYMENT_BACKEND="payments.services.RealProvider"):
            self.assertEqual(self.c.get(self.customer + "conversation/").status_code, 403)
            self.assertEqual(self.s.get(self.base + "overview/").status_code, 403)

    def test_reserved_login_is_explicitly_unavailable(self):
        r = APIClient().post(self.customer + "session/wechat/", {"code": "not-real"}, format="json")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.data["code"], "wechat_not_connected")

    def test_regular_customer_cannot_use_seller_workspace(self):
        buyer = get_user_model().objects.create_user(email="buyer@test.invalid")
        self.s.force_authenticate(buyer)
        self.assertEqual(self.s.get(self.base + "overview/").status_code, 403)


@override_settings(DEBUG=False, CONCIERGE_DEMO=True, PUBLIC_CONCIERGE_DEMO=True,
    ROOT_URLCONF="concierge.public_urls", MIDDLEWARE=middleware, TEMPLATES=templates,
    LANGUAGE_CODE="en", LANGUAGES=[("en", "English")], PUBLIC_DEMO_SEED_EMAIL="seed@demo.invalid",
    PUBLIC_DEMO_MAX_VISITORS=10, PAYMENT_BACKEND="payments.services.MockPaymentProvider",
    STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
              "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class PublicWorkbenchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model().objects.create_user(email="seed@demo.invalid", is_seller=True)
        Maker.objects.create(owner=user, name="Seed", slug="seed")

    def setUp(self):
        cache.clear()

    def test_public_bootstrap_csrf_and_customer_identity_separation(self):
        s = Client(enforce_csrf_checks=True)
        r = s.get("/seller/workbench/", secure=True)
        self.assertContains(r, 'Order operations')
        self.assertContains(r, 'No login needed')
        self.assertNotRegex(r.content.decode(), r"[\u4e00-\u9fff]")
        path = "/seller/workbench/api/invitations/"
        self.assertEqual(s.post(path, {}, secure=True).status_code, 403)
        r = s.post(path, '{"label":"Alex"}', content_type="application/json", secure=True,
            HTTP_ORIGIN="https://testserver", HTTP_X_CSRFTOKEN=s.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertEqual(r.status_code, 201)
        # Being logged into the seller browser still does not authenticate the customer API.
        self.assertEqual(s.get("/api/mini-store/v1/conversation/", secure=True).status_code, 401)
        other = Client()
        self.assertEqual(other.get("/customer/preview/", secure=True).status_code, 200)
        self.assertNotIn("public_demo_actor", other.session)
        self.assertIn(other.get("/seller/workbench/api/overview/", secure=True).status_code, (401,403))
