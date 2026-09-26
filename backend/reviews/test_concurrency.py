"""Real competing inserts on independent PostgreSQL connections."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.messages import get_messages
from django.db import connection, connections
from django.db.models.query import QuerySet
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from orders.models import Order
from orders.tests.factories import make_buyer, make_category, make_maker, make_order_item, make_product

from .models import Review


@skipUnless(connection.vendor == "postgresql", "Review races require PostgreSQL uniqueness semantics.")
@override_settings(
    LANGUAGE_CODE="en", SECURE_SSL_REDIRECT=False,
    STORAGES={**settings.STORAGES,
              "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
)
class ReviewConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.buyer = make_buyer()
        maker = make_maker("race-maker", "Race Maker")
        self.product = make_product(maker=maker, category=make_category(), slug="race-product")
        order = Order.objects.create(order_number="REVIEW-RACE", user=self.buyer, payment_status="paid")
        make_order_item(order=order, product=self.product)
        self.url = reverse("product_detail", args=[self.product.slug])
        self.api_url = reverse("review-list")

    def assert_race(self, modes):
        barrier = Barrier(2, timeout=15)
        original_exists = QuerySet.exists

        def synchronized_exists(queryset):
            exists = original_exists(queryset)
            if queryset.model is Review and not exists:
                # Both requests must pass the real duplicate pre-check before either inserts.
                barrier.wait()
            return exists

        clients = []
        for mode in modes:
            client = APIClient() if mode == "api" else Client()
            client.force_login(self.buyer)
            clients.append(client)

        def submit(mode, client, index):
            try:
                data = {"rating": "4", "title": f"Request {index}", "body": "Race test"}
                response = (client.post(self.api_url, {"product": self.product.slug, **data}, format="json")
                            if mode == "api" else client.post(self.url, data))
                if mode == "api":
                    feedback = str(response.data.get("detail", ""))
                else:
                    self.assertEqual(response.url, self.url)
                    feedback = " ".join(str(message) for message in get_messages(response.wsgi_request))
                self.assertEqual(Review.objects.count(), 1)
                # Also verify this connection remains usable for a subsequent write.
                Review.objects.filter(user=self.buyer, product=self.product).update(body="Connection usable")
                return response.status_code, feedback, data["title"]
            finally:
                connections["default"].close()

        with patch.object(QuerySet, "exists", synchronized_exists):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(submit, mode, client, index)
                           for index, (mode, client) in enumerate(zip(modes, clients))]
                results = [future.result(timeout=30) for future in futures]

        duplicate = "You have already reviewed this product."
        losers = [result for result in results if duplicate in result[1]]
        self.assertEqual(len(losers), 1, results)
        for mode, (status, feedback, title) in zip(modes, results):
            if duplicate in feedback:
                self.assertEqual(status, 400 if mode == "api" else 302)
            else:
                self.assertEqual(status, 201 if mode == "api" else 302)
                self.assertEqual(Review.objects.get().title, title)
                if mode == "storefront":
                    self.assertIn("Thank you for reviewing this piece.", feedback)
        self.assertEqual(Review.objects.count(), 1)
        response = clients[0].get(self.url)
        self.assertFalse(response.context["can_review"])

    def test_storefront_storefront_race(self):
        self.assert_race(("storefront", "storefront"))

    def test_api_api_race(self):
        self.assert_race(("api", "api"))

    def test_storefront_api_race(self):
        self.assert_race(("storefront", "api"))
