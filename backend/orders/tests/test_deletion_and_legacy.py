"""Category T/U/Z/W: FK deletion behaviour, legacy-order compatibility, and
the null-maker edge case.
"""
from decimal import Decimal

from django.db.models import ProtectedError
from django.test import TestCase

from orders import services
from orders.models import FulfillmentStatus, OrderItem, SellerFulfillment

from .factories import make_bare_order, make_maker


class MakerDeletionPolicyTests(TestCase):
    """Category T: a Maker referenced by a SellerFulfillment must not silently
    disappear -- PROTECT is the locked FK choice (see models.SellerFulfillment)."""

    def test_maker_referenced_by_a_fulfillment_cannot_be_deleted(self):
        order = make_bare_order()
        alice = make_maker("alice", "Alice")
        SellerFulfillment.objects.create(order=order, maker=alice)
        with self.assertRaises(ProtectedError):
            alice.delete()
        self.assertTrue(SellerFulfillment.objects.filter(order=order, maker=alice).exists())


class OrderDeletionTests(TestCase):
    """Category U: SellerFulfillment.order is CASCADE -- deleting the parent
    Order takes its fulfilments with it."""

    def test_deleting_order_cascades_its_fulfillments(self):
        order = make_bare_order()
        alice = make_maker("alice", "Alice")
        fulfillment = SellerFulfillment.objects.create(order=order, maker=alice)
        fulfillment_id = fulfillment.pk

        order.delete()
        self.assertFalse(SellerFulfillment.objects.filter(pk=fulfillment_id).exists())


class LegacyOrderCompatibilityTests(TestCase):
    """Category Z: an Order with zero SellerFulfillment rows -- exactly the
    state of every Order created before this migration -- must not make
    anything here crash, and must not be silently backfilled with invented
    fulfilments."""

    def test_sync_on_an_order_with_no_fulfillments_does_not_crash(self):
        order = make_bare_order()  # zero children, as any pre-migration order has
        result = services.sync_order_fulfillment_status(order)
        order.refresh_from_db()
        self.assertEqual(result, order.fulfillment_status)
        self.assertEqual(order.fulfillment_status, FulfillmentStatus.UNFULFILLED)
        self.assertEqual(order.seller_fulfillments.count(), 0)


class NullMakerEdgeCaseTests(TestCase):
    """Category W: OrderItem.maker is nullable at the schema level (SET_NULL,
    for when a Maker is later deleted -- see models.OrderItem). CONFIRMED
    impossible via today's create_order(), which always copies a required,
    PROTECTed product.maker (see checkout integration tests' snapshot check
    and orders.services.create_order). This simulates the schema-level
    possibility directly, without going through checkout, and proves
    create_seller_fulfillments deliberately does not invent a fulfilment with
    no seller."""

    def test_orderitem_with_no_maker_produces_no_fulfillment(self):
        order = make_bare_order()
        OrderItem.objects.create(
            order=order, product=None, maker=None,
            product_name="Legacy item (maker since deleted)",
            unit_price=Decimal("5.00"), quantity=1, line_total=Decimal("5.00"),
        )
        result = services.create_seller_fulfillments(order)
        self.assertEqual(result, [])
        self.assertEqual(SellerFulfillment.objects.filter(order=order).count(), 0)

    def test_maker_bearing_items_still_get_a_fulfillment_alongside_a_makerless_one(self):
        order = make_bare_order()
        alice = make_maker("alice", "Alice")
        OrderItem.objects.create(
            order=order, product=None, maker=None,
            product_name="Legacy item (maker since deleted)",
            unit_price=Decimal("5.00"), quantity=1, line_total=Decimal("5.00"),
        )
        OrderItem.objects.create(
            order=order, product=None, maker=alice, maker_name=alice.name,
            product_name="Alice's item",
            unit_price=Decimal("5.00"), quantity=1, line_total=Decimal("5.00"),
        )
        result = services.create_seller_fulfillments(order)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].maker_id, alice.pk)
