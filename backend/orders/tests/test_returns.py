"""Rules for buyer return requests and seller decisions (orders.returns)."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from orders.models import FulfillmentStatus, OrderStatus, PaymentStatus, ReturnReason, ReturnStatus
from orders.returns import (
    RETURN_WINDOW, decide_return, max_refund, open_return_count, request_return,
    return_eligibility_error, returnable_quantity,
)
from orders.services import create_seller_fulfillments

from .factories import (
    make_bare_order, make_buyer, make_category, make_maker, make_order_item, make_product,
    make_seller_user,
)


class ReturnTestBase(TestCase):
    def setUp(self):
        category = make_category()
        self.alice = make_maker("alice", "Alice", owner=make_seller_user("alice@example.test"))
        self.bob = make_maker("bob", "Bob", owner=make_seller_user("bob@example.test"))
        self.buyer = make_buyer()
        self.mug = make_product(maker=self.alice, category=category, slug="mug", price="30.00")
        self.scarf = make_product(maker=self.bob, category=category, slug="scarf", price="50.00")

        self.order = make_bare_order(status=OrderStatus.SHIPPED, payment_status=PaymentStatus.PAID)
        self.order.user = self.buyer
        self.order.save()
        self.item = make_order_item(order=self.order, product=self.mug, quantity=3)
        self.bob_item = make_order_item(order=self.order, product=self.scarf, quantity=1)
        create_seller_fulfillments(self.order)
        self.ship(self.alice)

    def ship(self, maker, when=None):
        self.order.seller_fulfillments.filter(maker=maker).update(
            status=FulfillmentStatus.FULFILLED, shipped_at=when or timezone.now())

    def request(self, **overrides):
        data = {"buyer": self.buyer, "quantity": 1, "reason": ReturnReason.CHANGED_MIND}
        data.update(overrides)
        return request_return(self.item, **data)


class RequestReturnTests(ReturnTestBase):
    def test_buyer_can_request_a_return_for_a_shipped_line(self):
        rr = self.request(quantity=2, details="  Too big  ")
        self.assertEqual(rr.status, ReturnStatus.REQUESTED)
        self.assertEqual(rr.maker, self.alice)
        self.assertEqual(rr.order, self.order)
        self.assertEqual(rr.details, "Too big")
        self.assertEqual(returnable_quantity(self.item), 1)
        self.assertEqual(open_return_count(self.alice), 1)
        self.assertEqual(open_return_count(self.bob), 0)

    def test_another_user_cannot_request_a_return(self):
        with self.assertRaises(PermissionDenied):
            self.request(buyer=make_buyer("stranger@example.test"))

    def test_unshipped_line_is_not_returnable(self):
        self.assertIsNotNone(return_eligibility_error(self.bob_item))
        with self.assertRaises(ValidationError):
            request_return(self.bob_item, buyer=self.buyer, quantity=1, reason=ReturnReason.FAULTY)

    def test_unpaid_refunded_and_cancelled_orders_are_not_returnable(self):
        for status, payment in ((OrderStatus.SHIPPED, PaymentStatus.UNPAID),
                                (OrderStatus.SHIPPED, PaymentStatus.REFUNDED),
                                (OrderStatus.CANCELLED, PaymentStatus.PAID)):
            with self.subTest(status=status, payment=payment):
                self.order.status, self.order.payment_status = status, payment
                self.order.save()
                with self.assertRaises(ValidationError):
                    self.request()

    def test_window_closes_after_thirty_days_plus_delivery(self):
        self.ship(self.alice, when=timezone.now() - RETURN_WINDOW - timedelta(minutes=1))
        with self.assertRaises(ValidationError):
            self.request()
        self.ship(self.alice, when=timezone.now() - RETURN_WINDOW + timedelta(hours=1))
        self.assertTrue(self.request().pk)

    def test_quantity_cannot_exceed_what_is_left(self):
        self.request(quantity=2)
        with self.assertRaises(ValidationError):
            self.request(quantity=2)
        with self.assertRaises(ValidationError):
            self.request(quantity=0)
        self.request(quantity=1)
        self.assertIsNotNone(return_eligibility_error(self.item))

    def test_rejected_units_can_be_requested_again(self):
        rr = self.request(quantity=3)
        decide_return(rr, acting_maker=self.alice, action="reject", seller_note="Used")
        self.assertEqual(returnable_quantity(self.item), 3)
        self.assertTrue(self.request(quantity=3).pk)

    def test_damage_needs_a_photo(self):
        with self.assertRaises(ValidationError) as ctx:
            self.request(reason=ReturnReason.DAMAGED)
        self.assertIn("photo", ctx.exception.message_dict)
        self.assertTrue(self.request(reason=ReturnReason.DAMAGED, photo="return-photo-x").pk)

    def test_made_to_order_cannot_be_returned_for_change_of_mind(self):
        self.mug.is_made_to_order = True
        self.mug.save()
        with self.assertRaises(ValidationError):
            self.request(reason=ReturnReason.CHANGED_MIND)
        self.assertTrue(self.request(reason=ReturnReason.FAULTY).pk)

    def test_legacy_order_without_fulfilment_rows_uses_order_status_and_date(self):
        self.order.seller_fulfillments.all().delete()
        self.order.placed_at = timezone.now() - timedelta(days=3)
        self.order.save()
        self.assertTrue(self.request().pk)
        self.order.placed_at = timezone.now() - RETURN_WINDOW - timedelta(days=1)
        self.order.save()
        self.assertIn("window", return_eligibility_error(self.item))
        self.order.status = OrderStatus.CONFIRMED
        self.order.save()
        self.assertIn("not been sent", return_eligibility_error(self.item))

    def test_unknown_reason_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.request(reason="bored")


class DecideReturnTests(ReturnTestBase):
    def test_only_the_lines_seller_can_decide(self):
        rr = self.request()
        with self.assertRaises(PermissionDenied):
            decide_return(rr, acting_maker=self.bob, action="approve")
        rr.refresh_from_db()
        self.assertEqual(rr.status, ReturnStatus.REQUESTED)

    def test_approve_then_refund_full_value_by_default(self):
        rr = self.request(quantity=2)
        rr = decide_return(rr, acting_maker=self.alice, action="approve")
        self.assertEqual(rr.status, ReturnStatus.APPROVED)
        self.assertIsNotNone(rr.decided_at)
        self.assertIsNone(rr.resolved_at)
        rr = decide_return(rr, acting_maker=self.alice, action="refund")
        self.assertEqual(rr.status, ReturnStatus.REFUNDED)
        self.assertEqual(rr.refund_amount, Decimal("60.00"))
        self.assertIsNotNone(rr.resolved_at)
        self.assertEqual(open_return_count(self.alice), 0)

    def test_partial_refund_and_limit(self):
        rr = self.request(quantity=1)
        with self.assertRaises(ValidationError):
            decide_return(rr, acting_maker=self.alice, action="refund", refund_amount=Decimal("30.01"))
        rr = decide_return(rr, acting_maker=self.alice, action="refund", refund_amount=Decimal("12.50"))
        self.assertEqual(rr.refund_amount, Decimal("12.50"))

    def test_refunds_never_exceed_the_line_total(self):
        first = decide_return(self.request(quantity=2), acting_maker=self.alice, action="refund")
        self.assertEqual(first.refund_amount, Decimal("60.00"))
        second = self.request(quantity=1)
        self.assertEqual(max_refund(second), Decimal("30.00"))

    def test_reject_needs_a_note(self):
        rr = self.request()
        with self.assertRaises(ValidationError):
            decide_return(rr, acting_maker=self.alice, action="reject", seller_note="  ")
        rr = decide_return(rr, acting_maker=self.alice, action="reject", seller_note="Shows wear")
        self.assertEqual(rr.status, ReturnStatus.REJECTED)
        self.assertEqual(rr.seller_note, "Shows wear")

    def test_settled_returns_are_final(self):
        rr = decide_return(self.request(), acting_maker=self.alice, action="replace")
        self.assertEqual(rr.status, ReturnStatus.REPLACED)
        for action in ("approve", "reject", "refund", "replace"):
            with self.subTest(action=action), self.assertRaises(ValidationError):
                decide_return(rr, acting_maker=self.alice, action=action, seller_note="x")

    def test_approved_return_cannot_be_approved_again(self):
        rr = decide_return(self.request(), acting_maker=self.alice, action="approve")
        with self.assertRaises(ValidationError):
            decide_return(rr, acting_maker=self.alice, action="approve")
