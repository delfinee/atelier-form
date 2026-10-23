import json
from unittest.mock import Mock, patch
from uuid import uuid4

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from orders.tests.factories import make_category, make_maker, make_product, make_seller_user
from . import planner
from .models import Change


def model_response(data):
    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": json.dumps(data)}}]}
    return response


@override_settings(SELLER_AGENT_USE_LLM=True, SELLER_AGENT_API_KEY="test-only-key",
                   SELLER_AGENT_MODEL="deepseek-flash", SELLER_AGENT_LLM_DAILY_LIMIT=500)
class SellerAIPlannerTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.products = [{"slug": "blue-mug", "name": "Blue Mug", "price": "20.00",
                          "currency": "SGD", "quantity": 7, "variants": [], "active": True,
                          "made_to_order": False, "low_stock": False}]

    @patch("seller_agent.planner.requests.post")
    def test_free_form_keyword_is_not_swallowed_by_guided_parser(self, post):
        post.return_value = model_response({"intent": "stock", "target": "blue-mug", "values": {"quantity": 12}})
        result = planner.plan("Please change the inventory of the blue mug to twelve", {}, self.products)
        self.assertEqual(result["engine"], "deepseek")
        self.assertEqual(result["values"]["quantity"], 12)
        post.assert_called_once()

    @patch("seller_agent.planner.requests.post")
    def test_exact_buttons_use_no_paid_calls(self, post):
        self.assertEqual(planner.plan("my products", {}, self.products)["engine"], "guided")
        self.assertEqual(planner.plan("set stock Blue Mug to 5", {}, self.products)["engine"], "guided")
        post.assert_not_called()

    @patch("seller_agent.planner.requests.post")
    def test_minimizes_order_data_and_preserves_context(self, post):
        post.return_value = model_response({"intent": "orders", "values": {}, "pending": True})
        orders = [{"uuid": "order-uuid", "order_number": "DEMO-1", "payment_status": "paid",
                   "can_ship": True, "customer_email": "never-send@example.invalid",
                   "shipping_address": {"address": "NEVER SEND THIS"},
                   "items": [{"product_name": "Blue Mug", "quantity": 1, "buyer_email": "PRIVATE"}]}]
        result = planner.plan("Which parcels can I dispatch?", {}, self.products, orders=orders,
                              history=[{"request": "show mugs", "intent": "products"}])
        sent = post.call_args.kwargs["json"]["messages"][-1]["content"]
        self.assertNotIn("never-send", sent)
        self.assertNotIn("NEVER SEND", sent)
        self.assertNotIn("PRIVATE", sent)
        self.assertIn("show mugs", sent)
        self.assertTrue(result["pending"])

    @patch("seller_agent.planner.requests.post")
    def test_rejects_unknown_target_and_authorization_fields(self, post):
        for payload in (
            {"intent": "price", "target": "another-shop", "values": {"price": "5"}},
            {"intent": "stock", "target": "blue-mug", "values": {"quantity": 8}, "confirmed": True},
            {"intent": "stock", "target": "blue-mug", "values": {"quantity": 8, "owner": "admin"}},
            {"intent": "stock", "target": "blue-mug", "values": {"quantity": 8, "variant": "foreign"}},
            {"intent": "listing", "values": {"category": "invented"}},
        ):
            post.return_value = model_response(payload)
            self.assertEqual(planner.plan("Please adjust that item", {}, self.products)["engine"], "guided")

    @patch("seller_agent.planner.requests.post")
    def test_timeout_empty_or_malformed_output_falls_back(self, post):
        post.side_effect = requests.Timeout()
        self.assertEqual(planner.plan("Help me choose a task", {}, self.products)["engine"], "guided")
        post.side_effect = None
        for content in ("", "not json", "[]"):
            post.return_value = model_response({})
            post.return_value.json.return_value["choices"][0]["message"]["content"] = content
            self.assertEqual(planner.plan("Help me choose a task", {}, self.products)["engine"], "guided")

    @override_settings(SELLER_AGENT_LLM_DAILY_LIMIT=1)
    @patch("seller_agent.planner.requests.post")
    def test_shared_daily_allowance_limits_paid_requests(self, post):
        post.return_value = model_response({"intent": "help", "reply": "Review low stock first."})
        self.assertEqual(planner.plan("What should I do?", {}, self.products)["engine"], "deepseek")
        self.assertEqual(planner.plan("Any other advice?", {}, self.products)["engine"], "guided")
        self.assertEqual(post.call_count, 1)


@override_settings(SELLER_AGENT_ENABLED=True, SELLER_AGENT_USE_LLM=True,
                   SELLER_AGENT_API_KEY="test-only-key", SELLER_AGENT_MODEL="deepseek-flash",
                   SELLER_AGENT_LLM_DAILY_LIMIT=500, ALLOWED_HOSTS=["testserver"])
class SellerAIIntegrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.seller = make_seller_user("ai-test@example.invalid")
        self.maker = make_maker("ai-studio", "AI Studio", owner=self.seller)
        self.category = make_category("ai-ceramics", "Ceramics")
        self.product = make_product(maker=self.maker, category=self.category, slug="ai-blue-mug",
                                    name="Blue Mug", price="20.00", stock_quantity=7)
        self.client = APIClient()
        self.client.force_authenticate(self.seller)
        self.base = "/api/seller-agent/v1/"
        self.conversation = self.client.post(self.base + "conversations/", {}, format="json").data["id"]
        self.url = self.base + "conversations/" + self.conversation + "/messages/"

    def send(self, text, request_id=None):
        return self.client.post(self.url, {"text": text, "request_id": request_id or str(uuid4())}, format="json")

    @patch("seller_agent.planner.requests.post")
    def test_natural_language_changes_require_explicit_confirmation_and_retry_is_free(self, post):
        post.return_value = model_response({"intent": "price", "target": "ai-blue-mug", "values": {"price": "18.00"}})
        request_id = str(uuid4())
        result = self.send("Could you reduce the blue mug price by ten percent?", request_id)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["engine"], "deepseek")
        self.product.refresh_from_db()
        self.assertEqual(str(self.product.price), "20.00")
        self.assertEqual(result.data["change"]["status"], "pending")
        self.assertEqual(self.send("Could you reduce the blue mug price by ten percent?", request_id).status_code, 200)
        self.assertEqual(post.call_count, 1)
        change_id = result.data["change"]["id"]
        confirm = self.base + "changes/" + change_id + "/confirm/"
        self.assertEqual(self.client.post(confirm, {"confirmed": False}, format="json").status_code, 400)
        self.assertEqual(self.client.post(confirm, {"confirmed": True}, format="json").status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(str(self.product.price), "18.00")

    @patch("seller_agent.planner.requests.post")
    def test_chinese_followup_gets_previous_target_without_auto_approval(self, post):
        post.return_value = model_response({"intent": "stock", "target": "ai-blue-mug", "values": {"quantity": 12}})
        self.assertEqual(self.send("请把蓝色杯子的库存改成十二个").status_code, 200)
        post.return_value = model_response({"intent": "stock", "target": "ai-blue-mug", "values": {"quantity": 14}})
        result = self.send("刚才那个改成十四个")
        sent = json.loads(post.call_args.kwargs["json"]["messages"][-1]["content"])
        self.assertEqual(sent["recent"][-1]["preview"]["target"], "ai-blue-mug")
        self.assertEqual(result.data["change"]["values"]["quantity"], 14)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 7)

    @patch("seller_agent.planner.requests.post")
    def test_advice_is_labelled_and_creates_no_change(self, post):
        post.return_value = model_response({"intent": "help", "reply": "Check low-stock items, then prepare paid orders."})
        result = self.send("What should I focus on today?")
        self.assertEqual(result.data["engine"], "deepseek")
        self.assertIn("AI suggestion", result.data["reply"])
        self.assertFalse(Change.objects.exists())
