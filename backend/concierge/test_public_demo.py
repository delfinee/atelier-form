"""Exercise the anonymous boundary with real middleware, CSRF and PostgreSQL."""
import json
from copy import deepcopy
from unittest.mock import patch, Mock
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from products.models import Maker, Category, Product, ProductVariant
from . import assistant
from .public_demo import SESSION_ACTOR_KEY

middleware = list(settings.MIDDLEWARE)
middleware.insert(middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1,
                  "concierge.public_demo.PublicDemoVisitorMiddleware")
templates = deepcopy(settings.TEMPLATES)
templates[0]["OPTIONS"]["context_processors"].remove("frontend.context_processors.frontend")


@override_settings(DEBUG=False, PUBLIC_CONCIERGE_DEMO=True, CONCIERGE_DEMO=True,
    PUBLIC_DEMO_SEED_EMAIL="seed@demo.invalid", PUBLIC_DEMO_MAX_VISITORS=10,
    ROOT_URLCONF="concierge.public_urls", MIDDLEWARE=middleware, TEMPLATES=templates,
    LANGUAGE_CODE="en", LANGUAGES=[("en", "English")], DEEPSEEK_API_KEY="",
    PAYMENT_BACKEND="payments.services.MockPaymentProvider",
    STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
              "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class PublicDemoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model().objects.create_user(email="seed@demo.invalid", is_seller=True)
        cls.maker = Maker.objects.create(name="Seed studio", slug="seed", owner=user)
        category = Category.objects.create(name="Ceramics", slug="ceramics")
        cls.product = Product.objects.create(name="Blue Bowl", slug="blue-bowl", maker=cls.maker,
            category=category, price="25.00", stock_quantity=10)
        cls.variant = ProductVariant.objects.create(product=cls.product, label="Blue", sku="BLUE", stock_quantity=5)

    def setUp(self):
        cache.clear()

    def visitor(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get("/seller/assistant/", secure=True, HTTP_ACCEPT_LANGUAGE="zh-CN")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html lang="en">')
        self.assertContains(response, 'Create order draft')
        self.assertContains(response, 'No login needed')
        self.assertNotRegex(response.content.decode(), r"[\u4e00-\u9fff]")
        return client

    def post(self, client, path, data):
        return client.post(path, json.dumps(data), content_type="application/json", secure=True,
            HTTP_ORIGIN="https://testserver", HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)

    def draft(self, client):
        c = self.post(client, "/seller/assistant/conversations/", {}).json()["id"]
        p = client.get("/seller/assistant/conversations/", secure=True).json()["catalog"][0]
        response = self.post(client, f"/seller/assistant/conversations/{c}/drafts/", {
            "request_id": str(uuid4()), "lines": [{"product": p["product"], "variant": p["variants"][0]["id"], "quantity": 2}],
            "email": "demo@example.test", "shipping_address": {"first_name": "Alex", "last_name": "Chen",
            "address_line_1": "100 Demo Road", "city": "Shanghai", "postal_code": "200000"}})
        self.assertEqual(response.status_code, 200, response.content)
        return c, response.json()

    def test_fresh_browser_gets_english_isolated_identity_and_stock(self):
        a, b = self.visitor(), self.visitor()
        self.assertNotEqual(a.session[SESSION_ACTOR_KEY], b.session[SESSION_ACTOR_KEY])
        guest = get_user_model().objects.get(pk=a.session[SESSION_ACTOR_KEY])
        self.assertFalse(guest.has_usable_password())
        self.assertFalse(guest.is_staff or guest.is_superuser)
        ca = a.get("/seller/assistant/conversations/", secure=True).json()["catalog"]
        cb = b.get("/seller/assistant/conversations/", secure=True).json()["catalog"]
        self.assertNotEqual(ca[0]["product"], cb[0]["product"])
        self.assertNotEqual(ca[0]["variants"][0]["id"], cb[0]["variants"][0]["id"])
        self.assertEqual(ca[0]["variants"][0]["stock"], 5)
        self.assertEqual(len(ca), 1)
        old_id = a.session[SESSION_ACTOR_KEY]
        a.get("/seller/assistant/", secure=True)
        self.assertEqual(a.session[SESSION_ACTOR_KEY], old_id)

    def test_full_order_flow_and_cross_visitor_access(self):
        a, b = self.visitor(), self.visitor()
        conversation, draft = self.draft(a)
        path = f'/seller/assistant/drafts/{draft["id"]}/action/'
        self.assertEqual(b.get(f"/seller/assistant/conversations/{conversation}/", secure=True).status_code, 404)
        self.assertEqual(self.post(b, path, {"action": "confirm", "confirmed": True}).status_code, 404)
        for action in ("confirm", "pay", "pack", "packed", "ship"):
            response = self.post(a, path, {"action": action, "confirmed": True,
                                          "carrier": "Demo Express", "tracking_number": "DEMO-TEST-123"})
            self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["order"]["status"], "shipped")
        self.assertEqual(response.json()["order"]["payment_status"], "paid")
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)
        bstock = b.get("/seller/assistant/conversations/", secure=True).json()["catalog"][0]["variants"][0]["stock"]
        self.assertEqual(bstock, 5)

    def test_csrf_and_minimal_public_routes(self):
        a = self.visitor()
        self.assertEqual(a.post("/seller/assistant/conversations/", {}, secure=True).status_code, 403)
        self.assertEqual(a.post("/seller/assistant/conversations/", {}, secure=True,
            HTTP_X_CSRFTOKEN=a.cookies[settings.CSRF_COOKIE_NAME].value, HTTP_ORIGIN="https://evil.invalid").status_code, 403)
        self.assertEqual(self.post(a, "/seller/assistant/conversations/", {}).status_code, 201)
        for path in ("/admin/", "/api/orders/", "/account/login/", "/.env", "/payments/mock/"):
            r = a.get(path, secure=True)
            self.assertEqual(r.status_code, 404)
            self.assertNotContains(r, "Traceback", status_code=404)
        # The shared test runner may have imported DRF views with the main
        # project's JWT authenticator (401); the public process uses sessions (403).
        self.assertIn(Client().get("/seller/assistant/conversations/", secure=True).status_code, (401, 403))

    @override_settings(PUBLIC_DEMO_MAX_VISITORS=1)
    def test_visitor_limit_preserves_existing_session(self):
        a = self.visitor()
        self.assertEqual(Client().get("/seller/assistant/", secure=True).status_code, 503)
        self.assertEqual(a.get("/seller/assistant/", secure=True).status_code, 200)

    def test_global_chat_budget_and_english_validation(self):
        a = self.visitor()
        conversation, draft = self.draft(a)
        response = self.post(a, f'/seller/assistant/drafts/{draft["id"]}/action/', {"action": "confirm"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Please confirm", response.content.decode())
        import time
        cache.set("public_concierge_chat_budget", [time.time()] * 120, 3600)
        with patch("concierge.assistant.suggest") as suggest:
            response = self.post(a, f"/seller/assistant/conversations/{conversation}/messages/", {"request_id": str(uuid4()), "text": "Hello"})
        self.assertEqual(response.status_code, 429)
        suggest.assert_not_called()

    @override_settings(DEEPSEEK_API_KEY="test")
    @patch("concierge.assistant.requests.post")
    def test_model_uses_english_and_fallback_is_english(self, post):
        post.return_value = Mock()
        post.return_value.json.return_value = {"choices": [{"message": {"content": '{"reply":"Hello", "lines":[]}'}}]}
        self.assertEqual(assistant.suggest("Hello", [])["reply"], "Hello")
        self.assertIn("Always reply in English", post.call_args.kwargs["json"]["messages"][0]["content"])
        with override_settings(DEEPSEEK_API_KEY=""):
            response = assistant.suggest("Hello", [])
        self.assertNotRegex(json.dumps(response, ensure_ascii=False), r"[\u4e00-\u9fff]")
