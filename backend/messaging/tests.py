"""Tests for buyer-seller messaging domain, permissions, persistence, and polling."""

import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from orders.models import Order, OrderItem
from products.models import Category, Maker, Product

from .models import Conversation, ConversationMessage
from . import services


class MessagingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.buyer = User.objects.create_user(
            email="buyer@test.example",
            password="Password123!",
            first_name="Alice",
            last_name="Buyer",
        )
        cls.other_buyer = User.objects.create_user(
            email="other_buyer@test.example",
            password="Password123!",
            first_name="Eve",
            last_name="Other",
        )

        cls.seller_user = User.objects.create_user(
            email="seller@test.example",
            password="Password123!",
            first_name="Master",
            last_name="Lin",
            is_seller=True,
        )
        cls.maker = Maker.objects.create(
            name="Lin Studio",
            slug="lin-studio",
            owner=cls.seller_user,
            discipline="Woodcraft",
            location="Hangzhou",
        )

        cls.other_seller_user = User.objects.create_user(
            email="other_seller@test.example",
            password="Password123!",
            first_name="Chen",
            last_name="Ceramics",
            is_seller=True,
        )
        cls.other_maker = Maker.objects.create(
            name="Chen Kiln",
            slug="chen-kiln",
            owner=cls.other_seller_user,
            discipline="Ceramics",
            location="Jingdezhen",
        )

        cls.category = Category.objects.create(name="Living", slug="living")
        cls.product = Product.objects.create(
            name="Walnut Keepsake Box",
            slug="walnut-keepsake-box",
            category=cls.category,
            maker=cls.maker,
            price=Decimal("120.00"),
        )
        cls.other_product = Product.objects.create(
            name="Celadon Tea Cup",
            slug="celadon-tea-cup",
            category=cls.category,
            maker=cls.other_maker,
            price=Decimal("80.00"),
        )

    def setUp(self):
        self.client = APIClient()

    def test_buyer_starts_conversation_and_sends_message(self):
        self.client.force_authenticate(user=self.buyer)

        # 1. Create/open thread with product
        resp = self.client.post("/api/conversations/", {"product": str(self.product.slug)})
        self.assertIn(resp.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED])
        conv_uuid = resp.data["uuid"]

        # Verify DB record
        conv = Conversation.objects.get(uuid=conv_uuid)
        self.assertEqual(conv.buyer, self.buyer)
        self.assertEqual(conv.maker, self.maker)
        self.assertEqual(conv.product, self.product)

        # 2. Buyer sends a message
        msg_resp = self.client.post(
            f"/api/conversations/{conv_uuid}/messages/",
            {"body": "Hello, is this keepsake box currently in stock?"},
        )
        self.assertEqual(msg_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(msg_resp.data["body"], "Hello, is this keepsake box currently in stock?")

        # Verify DB persistence (1 seller welcome greeting + 1 buyer message)
        self.assertEqual(ConversationMessage.objects.filter(conversation=conv).count(), 2)
        welcome_msg = ConversationMessage.objects.filter(conversation=conv).order_by("created_at").first()
        self.assertEqual(welcome_msg.sender, self.seller_user)
        self.assertIn("Welcome", welcome_msg.body)

        saved_msg = ConversationMessage.objects.get(uuid=msg_resp.data["uuid"])
        self.assertEqual(saved_msg.sender, self.buyer)
        self.assertIsNone(saved_msg.read_at)

    def test_seller_sees_message_and_replies_roundtrip(self):
        # Buyer starts conversation & sends message
        conv = Conversation.objects.create(buyer=self.buyer, maker=self.maker, product=self.product)
        ConversationMessage.objects.create(
            conversation=conv,
            sender=self.buyer,
            body="Can you engrave initials on the lid?",
        )

        # Seller authenticates
        self.client.force_authenticate(user=self.seller_user)

        # Seller lists seller conversations
        list_resp = self.client.get("/api/conversations/?role=seller")
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        conv_list = list_resp.data.get("items", list_resp.data) if isinstance(list_resp.data, dict) else list_resp.data
        conv_uuids = [c["uuid"] for c in conv_list]
        self.assertIn(str(conv.uuid), conv_uuids)

        # Seller reads thread messages
        msgs_resp = self.client.get(f"/api/conversations/{conv.uuid}/messages/")
        self.assertEqual(msgs_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(msgs_resp.data), 1)

        # Reading thread marks buyer message as read
        unread_buyer_msgs = ConversationMessage.objects.filter(
            conversation=conv, sender=self.buyer, read_at__isnull=True
        ).count()
        self.assertEqual(unread_buyer_msgs, 0)

        # Seller replies
        reply_resp = self.client.post(
            f"/api/conversations/{conv.uuid}/messages/",
            {"body": "Yes, we can engrave on the inner lid!"},
        )
        self.assertEqual(reply_resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(reply_resp.data["is_seller"])

        # Buyer polls for new message
        self.client.force_authenticate(user=self.buyer)
        buyer_poll = self.client.get(f"/api/conversations/{conv.uuid}/messages/")
        self.assertEqual(buyer_poll.status_code, status.HTTP_200_OK)
        self.assertEqual(len(buyer_poll.data), 2)
        self.assertEqual(buyer_poll.data[1]["body"], "Yes, we can engrave on the inner lid!")

    def test_polling_with_after_parameter(self):
        conv = Conversation.objects.create(buyer=self.buyer, maker=self.maker)
        m1 = services.send_message(conv, self.buyer, "First message")
        m2 = services.send_message(conv, self.seller_user, "Second message")

        self.client.force_authenticate(user=self.buyer)

        # Polling after m1's UUID should return only m2
        resp = self.client.get(f"/api/conversations/{conv.uuid}/messages/?after={m1.uuid}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["uuid"], str(m2.uuid))

    def test_buyer_cannot_access_other_buyers_conversation(self):
        conv = Conversation.objects.create(buyer=self.buyer, maker=self.maker)
        services.send_message(conv, self.buyer, "Private inquiry")

        # Other buyer attempts to access
        self.client.force_authenticate(user=self.other_buyer)
        resp = self.client.get(f"/api/conversations/{conv.uuid}/")
        self.assertIn(resp.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

        post_resp = self.client.post(
            f"/api/conversations/{conv.uuid}/messages/",
            {"body": "Malicious attempt"},
        )
        self.assertIn(post_resp.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_seller_cannot_access_other_makers_conversation(self):
        conv = Conversation.objects.create(buyer=self.buyer, maker=self.maker)
        services.send_message(conv, self.buyer, "Lin Studio order question")

        # Other seller attempts to read
        self.client.force_authenticate(user=self.other_seller_user)
        resp = self.client.get(f"/api/conversations/{conv.uuid}/")
        self.assertIn(resp.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_order_linked_conversation_validates_ownership(self):
        # Order owned by other_buyer
        order = Order.objects.create(
            user=self.other_buyer,
            order_number="AF-TEST-100",
            total=Decimal("120.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            maker=self.maker,
            product_name="Walnut Keepsake Box",
            line_total=Decimal("120.00"),
            unit_price=Decimal("120.00"),
            quantity=1,
        )

        # Buyer attempts to start conversation referencing Eve's order
        self.client.force_authenticate(user=self.buyer)
        resp = self.client.post("/api/conversations/", {
            "order": "AF-TEST-100",
            "maker": str(self.maker.slug),
        })
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_order_linked_conversation_validates_maker_in_order(self):
        # Order owned by buyer, but only containing items from Lin Studio
        order = Order.objects.create(
            user=self.buyer,
            order_number="AF-TEST-101",
            total=Decimal("120.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            maker=self.maker,
            product_name="Walnut Keepsake Box",
            line_total=Decimal("120.00"),
            unit_price=Decimal("120.00"),
            quantity=1,
        )

        # Buyer attempts to start conversation referencing this order with Chen Kiln (who is not in the order)
        self.client.force_authenticate(user=self.buyer)
        resp = self.client.post("/api/conversations/", {
            "order": "AF-TEST-101",
            "maker": str(self.other_maker.slug),
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_conversation_creation_requires_context_or_existing_thread(self):
        self.client.force_authenticate(user=self.buyer)

        resp = self.client.post("/api/conversations/", {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("maker or product", str(resp.data["detail"]))

    def test_generic_create_reuses_existing_thread_when_no_context_is_provided(self):
        existing = Conversation.objects.create(buyer=self.buyer, maker=self.maker)
        self.client.force_authenticate(user=self.buyer)

        resp = self.client.post("/api/conversations/", {})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["uuid"], str(existing.uuid))

    def test_seller_message_thread_does_not_render_raw_polled_message_html(self):
        conv = Conversation.objects.create(buyer=self.buyer, maker=self.maker, product=self.product)
        ConversationMessage.objects.create(
            conversation=conv,
            sender=self.buyer,
            body="<script>alert('boom')</script>",
        )

        self.client.force_login(self.seller_user)
        resp = self.client.get(reverse("seller_message_thread", args=[conv.uuid]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        html = resp.content.decode()
        self.assertNotIn("`${m.body}`", html)
        self.assertIn("textContent", html)

    def test_empty_and_oversized_messages_rejected(self):
        conv = Conversation.objects.create(buyer=self.buyer, maker=self.maker)
        self.client.force_authenticate(user=self.buyer)

        # Empty body
        resp_empty = self.client.post(f"/api/conversations/{conv.uuid}/messages/", {"body": "   "})
        self.assertEqual(resp_empty.status_code, status.HTTP_400_BAD_REQUEST)

        # Oversized body (> 3000 chars)
        resp_big = self.client.post(f"/api/conversations/{conv.uuid}/messages/", {"body": "A" * 3001})
        self.assertEqual(resp_big.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_cannot_create_or_send(self):
        resp = self.client.post("/api/conversations/", {"maker": str(self.maker.slug)})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
