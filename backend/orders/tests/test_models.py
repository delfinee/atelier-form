"""Category A/B: SellerFulfillment model creation, defaults, and the
(order, maker) database-level uniqueness constraint.
"""
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from orders.models import FulfillmentStatus, SellerFulfillment

from .factories import make_bare_order, make_maker


class SellerFulfillmentCreationTests(TestCase):
    def setUp(self):
        self.alice = make_maker("alice", "Alice")
        self.order = make_bare_order()

    def test_create_with_all_fields(self):
        shipped = timezone.now()
        fulfillment = SellerFulfillment.objects.create(
            order=self.order, maker=self.alice, status=FulfillmentStatus.FULFILLED,
            carrier="DHL", tracking_number="ALICE123", shipped_at=shipped,
        )
        fulfillment.refresh_from_db()
        self.assertEqual(fulfillment.order_id, self.order.pk)
        self.assertEqual(fulfillment.maker_id, self.alice.pk)
        self.assertEqual(fulfillment.status, FulfillmentStatus.FULFILLED)
        self.assertEqual(fulfillment.carrier, "DHL")
        self.assertEqual(fulfillment.tracking_number, "ALICE123")
        self.assertIsNotNone(fulfillment.shipped_at)

    def test_defaults(self):
        fulfillment = SellerFulfillment.objects.create(order=self.order, maker=self.alice)
        self.assertEqual(fulfillment.status, FulfillmentStatus.UNFULFILLED)
        self.assertEqual(fulfillment.carrier, "")
        self.assertEqual(fulfillment.tracking_number, "")
        self.assertIsNone(fulfillment.shipped_at)


class SellerFulfillmentUniquenessTests(TestCase):
    def setUp(self):
        self.alice = make_maker("alice", "Alice")
        self.bob = make_maker("bob", "Bob")
        self.order = make_bare_order()

    def test_duplicate_order_and_maker_rejected(self):
        SellerFulfillment.objects.create(order=self.order, maker=self.alice)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SellerFulfillment.objects.create(order=self.order, maker=self.alice)
        # exactly one survives -- the rejected insert did not partially land
        self.assertEqual(
            SellerFulfillment.objects.filter(order=self.order, maker=self.alice).count(), 1)

    def test_same_maker_across_different_orders_is_allowed(self):
        other_order = make_bare_order()
        SellerFulfillment.objects.create(order=self.order, maker=self.alice)
        # must not raise -- uniqueness is per (order, maker), not per maker
        SellerFulfillment.objects.create(order=other_order, maker=self.alice)
        self.assertEqual(SellerFulfillment.objects.filter(maker=self.alice).count(), 2)

    def test_different_makers_in_the_same_order_is_allowed(self):
        SellerFulfillment.objects.create(order=self.order, maker=self.alice)
        # must not raise -- uniqueness is per (order, maker), not per order
        SellerFulfillment.objects.create(order=self.order, maker=self.bob)
        self.assertEqual(SellerFulfillment.objects.filter(order=self.order).count(), 2)
