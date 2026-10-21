"""Buyer progress must follow seller fulfilment without changing commerce state."""
from django.test import TestCase

from orders.models import FulfillmentStatus, OrderStatus, PaymentStatus, SellerFulfillment
from orders.services import update_seller_fulfillment
from orders.tests.factories import (
    make_bare_order, make_category, make_maker, make_order_item, make_product,
)
from frontend.order_progress import buyer_shipping_progress


class BuyerShippingProgressTests(TestCase):
    def setUp(self):
        category = make_category()
        self.alice = make_maker("alice-progress", "Alice")
        self.bob = make_maker("bob-progress", "Bob")
        self.a_product = make_product(maker=self.alice, category=category, slug="a-progress")
        self.b_product = make_product(maker=self.bob, category=category, slug="b-progress")
        self.order = make_bare_order(status=OrderStatus.CONFIRMED, payment_status=PaymentStatus.PAID)
        make_order_item(order=self.order, product=self.a_product)
        self.a = SellerFulfillment.objects.create(order=self.order, maker=self.alice)

    def progress(self):
        self.order.refresh_from_db()
        return buyer_shipping_progress(self.order)

    def test_single_seller_dispatch_updates_buyer_progress(self):
        update_seller_fulfillment(self.a, acting_maker=self.alice, status=FulfillmentStatus.FULFILLED,
                                  carrier="DHL", tracking_number="A123")
        result = self.progress()
        self.assertEqual(result["label"], "On its way")
        self.assertTrue(result["timeline"][3]["done"])
        self.assertFalse(result["timeline"][4]["done"])
        self.assertEqual(result["shipments"][0].tracking_number, "A123")
        # The presentation layer must never rewrite the commercial state.
        self.assertEqual(self.order.status, OrderStatus.CONFIRMED)

    def test_one_of_two_sellers_does_not_mark_whole_order_shipped(self):
        make_order_item(order=self.order, product=self.b_product)
        SellerFulfillment.objects.create(order=self.order, maker=self.bob)
        update_seller_fulfillment(self.a, acting_maker=self.alice, status=FulfillmentStatus.FULFILLED)
        result = self.progress()
        self.assertEqual(result["label"], "Partially dispatched")
        self.assertFalse(result["timeline"][3]["done"])

    def test_all_sellers_fulfilled_completes_dispatch(self):
        make_order_item(order=self.order, product=self.b_product)
        b = SellerFulfillment.objects.create(order=self.order, maker=self.bob)
        update_seller_fulfillment(self.a, acting_maker=self.alice, status=FulfillmentStatus.FULFILLED)
        update_seller_fulfillment(b, acting_maker=self.bob, status=FulfillmentStatus.FULFILLED)
        self.assertTrue(self.progress()["timeline"][3]["done"])

    def test_legacy_missing_seller_row_cannot_claim_complete_dispatch(self):
        make_order_item(order=self.order, product=self.b_product)
        update_seller_fulfillment(self.a, acting_maker=self.alice, status=FulfillmentStatus.FULFILLED)
        result = self.progress()
        self.assertEqual(result["label"], "Confirmed")
        self.assertFalse(result["timeline"][3]["done"])

    def test_cancelled_order_takes_precedence(self):
        update_seller_fulfillment(self.a, acting_maker=self.alice, status=FulfillmentStatus.FULFILLED)
        self.order.status = OrderStatus.CANCELLED
        self.order.save(update_fields=["status"])
        result = self.progress()
        self.assertEqual(result["label"], "Cancelled")
        self.assertEqual(len(result["timeline"]), 2)

    def test_backward_correction_removes_dispatched_progress(self):
        update_seller_fulfillment(self.a, acting_maker=self.alice, status=FulfillmentStatus.FULFILLED)
        update_seller_fulfillment(self.a, acting_maker=self.alice, status=FulfillmentStatus.UNFULFILLED)
        result = self.progress()
        self.assertEqual(result["label"], "Confirmed")
        self.assertFalse(result["timeline"][3]["done"])

    def test_unpaid_record_does_not_gain_shipping_progress_from_stale_data(self):
        self.a.status = FulfillmentStatus.FULFILLED
        self.a.save(update_fields=["status"])
        self.order.payment_status = PaymentStatus.UNPAID
        self.order.save(update_fields=["payment_status"])
        self.assertEqual(self.progress()["label"], "Confirmed")
