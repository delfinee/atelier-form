"""CP-M6: dispatch eligibility, delivery confirmation and shipment notices.

Covers the service rules (orders.services), the seller API's error contract,
and the Order-first locking that keeps concurrent requests consistent. The
concurrency tests at the bottom run two real database connections against
PostgreSQL and prove the second request genuinely waits on a row lock --
not merely that FOR UPDATE appears in the SQL.
"""
import threading
import time
from datetime import timedelta
from unittest import mock, skipUnless

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from content import services as content_services
from orders import services
from orders.models import (
    FulfillmentStatus, Order, OrderItem, OrderStatus, PaymentStatus, SellerFulfillment,
)

from .factories import (
    make_bare_order, make_category, make_maker, make_order_item, make_product, make_seller_user,
)

UNFULFILLED, PARTIAL, FULFILLED = (
    FulfillmentStatus.UNFULFILLED, FulfillmentStatus.PARTIAL, FulfillmentStatus.FULFILLED)

PAID_CONFIRMED = {"status": OrderStatus.CONFIRMED, "payment_status": PaymentStatus.PAID}

# (label, Order.status, Order.payment_status) -- none of these may be dispatched.
INELIGIBLE_ORDERS = [
    ("unpaid", OrderStatus.PENDING, PaymentStatus.UNPAID),
    ("payment pending", OrderStatus.PENDING, PaymentStatus.PENDING),
    ("payment failed", OrderStatus.CANCELLED, PaymentStatus.FAILED),
    ("refunded", OrderStatus.CONFIRMED, PaymentStatus.REFUNDED),
    ("paid but cancelled", OrderStatus.CANCELLED, PaymentStatus.PAID),
    ("paid but still pending", OrderStatus.PENDING, PaymentStatus.PAID),
    ("paid and delivered", OrderStatus.DELIVERED, PaymentStatus.PAID),
]
ELIGIBLE_ORDER_STATUSES = [OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.SHIPPED]

# Patched where the service resolves them (imported at call time).
SHIPPED_NOTICE = "content.services.send_order_shipped"
DELIVERED_NOTICE = "content.services.send_order_delivered"


class FulfilmentSafetyFixtures:
    """Small builders shared by the classes in this module."""

    def make_catalogue(self):
        self.category = make_category()
        self.alice = make_maker("alice", "Alice Studio")
        self.bob = make_maker("bob", "Bob Workshop")
        self.alice_product = make_product(maker=self.alice, category=self.category,
                                          slug="alice-vase", name="Alice Vase")
        self.bob_product = make_product(maker=self.bob, category=self.category,
                                        slug="bob-stool", name="Bob Stool")

    def single_seller_order(self, *, fulfilment_status=UNFULFILLED, **order_fields):
        order = make_bare_order(**(order_fields or PAID_CONFIRMED))
        make_order_item(order=order, product=self.alice_product)
        fulfilment = SellerFulfillment.objects.create(
            order=order, maker=self.alice, status=fulfilment_status)
        return order, fulfilment

    def shared_order(self, **order_fields):
        order = make_bare_order(**(order_fields or PAID_CONFIRMED))
        make_order_item(order=order, product=self.alice_product)
        make_order_item(order=order, product=self.bob_product)
        alice_f = SellerFulfillment.objects.create(order=order, maker=self.alice)
        bob_f = SellerFulfillment.objects.create(order=order, maker=self.bob)
        return order, alice_f, bob_f

    @staticmethod
    def snapshot(fulfilment):
        row = SellerFulfillment.objects.get(pk=fulfilment.pk)
        return (row.status, row.carrier, row.tracking_number, row.shipped_at)

    @staticmethod
    def mark_shipped(fulfilment, *, shipped_at, carrier="", tracking_number=""):
        """Put a fulfilment into a historical shipped state directly."""
        SellerFulfillment.objects.filter(pk=fulfilment.pk).update(
            status=FULFILLED, shipped_at=shipped_at,
            carrier=carrier, tracking_number=tracking_number)
        fulfilment.refresh_from_db()


# ---------------------------------------------------------------------------
# G4 -- dispatch eligibility
# ---------------------------------------------------------------------------

class DispatchEligibilityTests(FulfilmentSafetyFixtures, TestCase):
    def setUp(self):
        self.make_catalogue()

    def test_forward_transitions_are_rejected_on_ineligible_orders(self):
        for label, order_status, payment_status in INELIGIBLE_ORDERS:
            for target in (PARTIAL, FULFILLED):
                with self.subTest(order=label, target=target):
                    order, f = self.single_seller_order(status=order_status,
                                                        payment_status=payment_status)
                    parent_before = order.fulfillment_status
                    with mock.patch(SHIPPED_NOTICE) as notice, \
                            self.captureOnCommitCallbacks(execute=True):
                        with self.assertRaises(ValidationError) as ctx:
                            services.update_seller_fulfillment(
                                f, acting_maker=self.alice, status=target,
                                carrier="DHL", tracking_number="DHL-1")
                    self.assertIn("status", ctx.exception.message_dict)
                    # Nothing from the rejected request is applied, not even carrier/tracking.
                    self.assertEqual(self.snapshot(f), (UNFULFILLED, "", "", None))
                    order.refresh_from_db()
                    self.assertEqual(order.fulfillment_status, parent_before)
                    notice.assert_not_called()

    def test_forward_transitions_are_allowed_on_eligible_orders(self):
        for order_status in ELIGIBLE_ORDER_STATUSES:
            with self.subTest(order_status=order_status):
                order, f = self.single_seller_order(status=order_status,
                                                    payment_status=PaymentStatus.PAID)
                services.update_seller_fulfillment(f, acting_maker=self.alice, status=FULFILLED)
                status, _, _, shipped_at = self.snapshot(f)
                self.assertEqual(status, FULFILLED)
                self.assertIsNotNone(shipped_at)
                order.refresh_from_db()
                self.assertEqual(order.fulfillment_status, FULFILLED)

    def test_partial_counts_as_dispatch(self):
        order, f = self.single_seller_order()
        services.update_seller_fulfillment(f, acting_maker=self.alice, status=PARTIAL)
        self.assertEqual(self.snapshot(f), (PARTIAL, "", "", None))

        # Once the order is cancelled, moving PARTIAL -> FULFILLED is still a dispatch.
        Order.objects.filter(pk=order.pk).update(status=OrderStatus.CANCELLED)
        with self.assertRaises(ValidationError):
            services.update_seller_fulfillment(f, acting_maker=self.alice, status=FULFILLED)
        self.assertEqual(self.snapshot(f), (PARTIAL, "", "", None))

    def test_same_status_tracking_correction_is_allowed_after_a_refund(self):
        shipped_at = timezone.now() - timedelta(days=2)
        _, f = self.single_seller_order(status=OrderStatus.CONFIRMED,
                                        payment_status=PaymentStatus.REFUNDED)
        self.mark_shipped(f, shipped_at=shipped_at, carrier="SF Express", tracking_number="OLD")

        services.update_seller_fulfillment(f, acting_maker=self.alice, status=FULFILLED,
                                           tracking_number="NEW")
        self.assertEqual(self.snapshot(f), (FULFILLED, "SF Express", "NEW", shipped_at))

    def test_carrier_and_tracking_only_updates_are_allowed_on_ineligible_orders(self):
        for label, order_status, payment_status in INELIGIBLE_ORDERS:
            with self.subTest(order=label):
                _, f = self.single_seller_order(status=order_status, payment_status=payment_status)
                services.update_seller_fulfillment(f, acting_maker=self.alice,
                                                   carrier="DHL", tracking_number="DHL-9")
                self.assertEqual(self.snapshot(f), (UNFULFILLED, "DHL", "DHL-9", None))

    def test_backward_transition_keeps_first_shipped_at(self):
        order, f = self.single_seller_order()
        services.update_seller_fulfillment(f, acting_maker=self.alice, status=FULFILLED)
        first_shipped_at = self.snapshot(f)[3]

        services.update_seller_fulfillment(f, acting_maker=self.alice, status=UNFULFILLED)
        self.assertEqual(self.snapshot(f), (UNFULFILLED, "", "", first_shipped_at))
        order.refresh_from_db()
        self.assertEqual(order.fulfillment_status, UNFULFILLED)

        services.update_seller_fulfillment(f, acting_maker=self.alice, status=FULFILLED)
        self.assertEqual(self.snapshot(f), (FULFILLED, "", "", first_shipped_at))

    def test_backward_transition_is_allowed_on_ineligible_orders(self):
        shipped_at = timezone.now() - timedelta(days=1)
        _, f = self.single_seller_order(status=OrderStatus.CANCELLED,
                                        payment_status=PaymentStatus.PAID)
        self.mark_shipped(f, shipped_at=shipped_at)

        services.update_seller_fulfillment(f, acting_maker=self.alice, status=UNFULFILLED)
        self.assertEqual(self.snapshot(f), (UNFULFILLED, "", "", shipped_at))

    def test_ownership_is_checked_before_eligibility(self):
        _, _, bob_f = self.shared_order(status=OrderStatus.PENDING,
                                        payment_status=PaymentStatus.UNPAID)
        with self.assertRaises(PermissionDenied):
            services.update_seller_fulfillment(bob_f, acting_maker=self.alice, status=FULFILLED)
        self.assertEqual(self.snapshot(bob_f), (UNFULFILLED, "", "", None))

    def test_status_validation_is_checked_before_eligibility(self):
        _, f = self.single_seller_order(status=OrderStatus.PENDING,
                                        payment_status=PaymentStatus.UNPAID)
        with self.assertRaises(ValidationError) as ctx:
            services.update_seller_fulfillment(f, acting_maker=self.alice, status="flying")
        self.assertEqual(ctx.exception.message_dict["status"], ["Invalid fulfilment status."])

    def test_shared_order_dispatch_touches_only_the_acting_sellers_fulfilment(self):
        order, alice_f, bob_f = self.shared_order()
        services.update_seller_fulfillment(alice_f, acting_maker=self.alice, status=FULFILLED,
                                           carrier="ZTO", tracking_number="ZTO-1")
        self.assertEqual(self.snapshot(bob_f), (UNFULFILLED, "", "", None))
        order.refresh_from_db()
        self.assertEqual(order.fulfillment_status, PARTIAL)


class StaleInstanceTests(FulfilmentSafetyFixtures, TestCase):
    """Decisions are made on fresh, locked rows -- never on the caller's copy."""

    def setUp(self):
        self.make_catalogue()

    def test_stale_fulfilment_is_refreshed_before_evaluating_the_transition(self):
        _, f = self.single_seller_order()
        stale = SellerFulfillment.objects.get(pk=f.pk)  # loaded before another request shipped it
        shipped_at = timezone.now() - timedelta(hours=1)
        self.mark_shipped(f, shipped_at=shipped_at, tracking_number="FIRST")
        self.assertIsNone(stale.shipped_at)

        with mock.patch(SHIPPED_NOTICE) as notice, self.captureOnCommitCallbacks(execute=True):
            services.update_seller_fulfillment(stale, acting_maker=self.alice, status=FULFILLED)

        notice.assert_not_called()  # the first request already announced this shipment
        self.assertEqual(stale.shipped_at, shipped_at)  # caller's instance refreshed in place
        self.assertEqual(self.snapshot(f), (FULFILLED, "", "FIRST", shipped_at))

    def test_stale_order_cannot_bypass_eligibility(self):
        order, f = self.single_seller_order()
        f = SellerFulfillment.objects.select_related("order").get(pk=f.pk)
        Order.objects.filter(pk=order.pk).update(status=OrderStatus.CANCELLED)
        self.assertEqual(f.order.status, OrderStatus.CONFIRMED)  # the in-memory copy is stale

        with self.assertRaises(ValidationError):
            services.update_seller_fulfillment(f, acting_maker=self.alice, status=FULFILLED)
        self.assertEqual(self.snapshot(f), (UNFULFILLED, "", "", None))

    def test_stale_order_is_not_delivered_twice(self):
        order, _ = self.single_seller_order(fulfilment_status=FULFILLED)
        stale = Order.objects.get(pk=order.pk)
        Order.objects.filter(pk=order.pk).update(status=OrderStatus.DELIVERED)

        with mock.patch(DELIVERED_NOTICE) as notice, self.captureOnCommitCallbacks(execute=True):
            services.mark_order_delivered(stale, acting_maker=self.alice)

        notice.assert_not_called()
        self.assertEqual(stale.status, OrderStatus.DELIVERED)


class LockingQueryTests(FulfilmentSafetyFixtures, TestCase):
    """Supporting evidence only: the locks are requested, Order first.
    ConcurrencyTests below is what shows they actually serialise requests."""

    def setUp(self):
        self.make_catalogue()

    def locked_tables(self, queries):
        locked = [q["sql"] for q in queries if "FOR UPDATE" in q["sql"]]
        return [("order" if 'FROM "orders_order"' in sql else
                 "fulfilment" if 'FROM "orders_sellerfulfillment"' in sql else sql)
                for sql in locked]

    def test_update_locks_order_before_fulfilment(self):
        _, f = self.single_seller_order()
        with CaptureQueriesContext(connection) as ctx:
            services.update_seller_fulfillment(f, acting_maker=self.alice, status=FULFILLED)
        self.assertEqual(self.locked_tables(ctx.captured_queries), ["order", "fulfilment"])

    def test_delivery_locks_order_before_fulfilments(self):
        order, _ = self.single_seller_order(fulfilment_status=FULFILLED)
        with CaptureQueriesContext(connection) as ctx:
            services.mark_order_delivered(order, acting_maker=self.alice)
        self.assertEqual(self.locked_tables(ctx.captured_queries), ["order", "fulfilment"])


# ---------------------------------------------------------------------------
# G5 -- delivery confirmation
# ---------------------------------------------------------------------------

class DeliveryConfirmationTests(FulfilmentSafetyFixtures, TestCase):
    def setUp(self):
        self.make_catalogue()

    def assert_rejected(self, order, *, error=ValidationError, acting_maker=None):
        status_before, fulfilment_status_before = order.status, order.fulfillment_status
        with mock.patch(DELIVERED_NOTICE) as notice, self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(error):
                services.mark_order_delivered(order, acting_maker=acting_maker or self.alice)
        row = Order.objects.get(pk=order.pk)
        self.assertEqual((row.status, row.fulfillment_status),
                         (status_before, fulfilment_status_before))
        notice.assert_not_called()

    def test_single_seller_shipped_order_can_be_confirmed_delivered(self):
        order, _ = self.single_seller_order(fulfilment_status=FULFILLED)
        fulfilment_status_before = order.fulfillment_status
        with mock.patch(DELIVERED_NOTICE) as notice, self.captureOnCommitCallbacks(execute=True):
            returned = services.mark_order_delivered(order, acting_maker=self.alice)

        self.assertIs(returned, order)
        row = Order.objects.get(pk=order.pk)
        self.assertEqual(row.status, OrderStatus.DELIVERED)
        self.assertEqual(row.fulfillment_status, fulfilment_status_before)  # never written here
        notice.assert_called_once()
        self.assertEqual(notice.call_args.args[0].pk, order.pk)

    def test_repeat_confirmation_is_idempotent_and_does_not_notify_again(self):
        order, _ = self.single_seller_order(fulfilment_status=FULFILLED)
        with mock.patch(DELIVERED_NOTICE) as notice:
            with self.captureOnCommitCallbacks(execute=True):
                services.mark_order_delivered(order, acting_maker=self.alice)
            with self.captureOnCommitCallbacks(execute=True):
                services.mark_order_delivered(order, acting_maker=self.alice)
        notice.assert_called_once()
        self.assertEqual(Order.objects.get(pk=order.pk).status, OrderStatus.DELIVERED)

    def test_multi_seller_order_cannot_be_confirmed_by_one_seller(self):
        order, alice_f, bob_f = self.shared_order()
        for f in (alice_f, bob_f):
            self.mark_shipped(f, shipped_at=timezone.now())
        self.assert_rejected(order)
        self.assert_rejected(order, acting_maker=self.bob)

    def test_item_from_another_seller_without_a_fulfilment_blocks_delivery(self):
        order, _ = self.single_seller_order(fulfilment_status=FULFILLED)
        make_order_item(order=order, product=self.bob_product)  # legacy line, no Bob fulfilment
        self.assert_rejected(order)

    def test_maker_less_item_blocks_delivery(self):
        order, _ = self.single_seller_order(fulfilment_status=FULFILLED)
        OrderItem.objects.create(order=order, product=None, maker=None, product_name="Old piece",
                                 unit_price=10, quantity=1, line_total=10)
        self.assert_rejected(order)

    def test_order_without_items_cannot_be_confirmed(self):
        order = make_bare_order(**PAID_CONFIRMED)
        SellerFulfillment.objects.create(order=order, maker=self.alice, status=FULFILLED)
        self.assert_rejected(order)

    def test_fulfilment_must_already_be_fulfilled(self):
        for fulfilment_status in (UNFULFILLED, PARTIAL):
            with self.subTest(fulfilment_status=fulfilment_status):
                order, _ = self.single_seller_order(fulfilment_status=fulfilment_status)
                self.assert_rejected(order)

    def test_ineligible_orders_cannot_be_confirmed(self):
        for label, order_status, payment_status in INELIGIBLE_ORDERS:
            if order_status == OrderStatus.DELIVERED:
                continue  # already delivered is the idempotent case
            with self.subTest(order=label):
                order, _ = self.single_seller_order(fulfilment_status=FULFILLED,
                                                    status=order_status,
                                                    payment_status=payment_status)
                self.assert_rejected(order)

    def test_seller_without_a_fulfilment_on_the_order_is_denied(self):
        order, _ = self.single_seller_order(fulfilment_status=FULFILLED)
        self.assert_rejected(order, error=PermissionDenied, acting_maker=self.bob)

    def test_legacy_order_without_fulfilment_rows_is_denied(self):
        order = make_bare_order(**PAID_CONFIRMED)
        make_order_item(order=order, product=self.alice_product)
        self.assert_rejected(order, error=PermissionDenied)

    def test_integrity_is_checked_before_the_idempotent_return(self):
        order, alice_f, bob_f = self.shared_order(status=OrderStatus.DELIVERED,
                                                  payment_status=PaymentStatus.PAID)
        self.assert_rejected(order)


# ---------------------------------------------------------------------------
# G6 -- shipment notifications
# ---------------------------------------------------------------------------

class ShipmentNotificationTests(FulfilmentSafetyFixtures, TestCase):
    def setUp(self):
        self.make_catalogue()

    def update(self, f, **changes):
        with mock.patch(SHIPPED_NOTICE) as notice, self.captureOnCommitCallbacks(execute=True):
            services.update_seller_fulfillment(f, acting_maker=f.maker, **changes)
        return notice

    def test_first_shipment_of_a_single_seller_order_is_a_whole_order_notice(self):
        _, f = self.single_seller_order()
        notice = self.update(f, status=FULFILLED, carrier="SF Express", tracking_number="SF-1")
        notice.assert_called_once()
        self.assertEqual(notice.call_args.args[0].pk, f.pk)
        self.assertEqual(notice.call_args.kwargs, {"whole_order": True})

    def test_first_shipment_of_a_shared_order_is_a_partial_notice(self):
        _, alice_f, _ = self.shared_order()
        notice = self.update(alice_f, status=FULFILLED)
        notice.assert_called_once()
        self.assertEqual(notice.call_args.kwargs, {"whole_order": False})

    def test_another_sellers_item_without_a_fulfilment_makes_the_notice_partial(self):
        order, f = self.single_seller_order()
        make_order_item(order=order, product=self.bob_product)
        notice = self.update(f, status=FULFILLED)
        self.assertEqual(notice.call_args.kwargs, {"whole_order": False})

    def test_each_seller_is_announced_once(self):
        _, alice_f, bob_f = self.shared_order()
        self.update(alice_f, status=FULFILLED).assert_called_once()
        self.update(bob_f, status=FULFILLED).assert_called_once()

    def test_no_notice_for_partial_repeat_tracking_or_backward_updates(self):
        _, f = self.single_seller_order()
        self.update(f, status=PARTIAL).assert_not_called()
        self.update(f, status=FULFILLED).assert_called_once()
        self.update(f, status=FULFILLED).assert_not_called()
        self.update(f, tracking_number="LATER").assert_not_called()
        self.update(f, status=UNFULFILLED).assert_not_called()
        self.update(f, status=FULFILLED).assert_not_called()  # shipped_at already recorded

    def test_notice_is_deferred_until_commit(self):
        _, f = self.single_seller_order()
        with mock.patch(SHIPPED_NOTICE) as notice, \
                self.captureOnCommitCallbacks(execute=False) as callbacks:
            services.update_seller_fulfillment(f, acting_maker=self.alice, status=FULFILLED)
            notice.assert_not_called()
        self.assertEqual(len(callbacks), 1)
        notice.assert_not_called()


class ShipmentNoticeWordingTests(FulfilmentSafetyFixtures, TestCase):
    def setUp(self):
        self.make_catalogue()
        self.sender = mock.Mock()
        patcher = mock.patch("content.services.get_email_sender", return_value=self.sender)
        patcher.start()
        self.addCleanup(patcher.stop)

    def sent(self):
        self.sender.send.assert_called_once()
        return self.sender.send.call_args.kwargs

    def test_whole_order_wording_includes_carrier_and_tracking(self):
        order, f = self.single_seller_order()
        self.mark_shipped(f, shipped_at=timezone.now(), carrier="SF Express", tracking_number="SF-1")
        content_services.send_order_shipped(f, whole_order=True)
        message = self.sent()
        self.assertEqual(message["to"], order.customer_email)
        self.assertEqual(message["subject"], f"Your order {order.order_number} has shipped")
        self.assertIn("SF Express", message["body"])
        self.assertIn("SF-1", message["body"])
        self.assertNotIn("Part of", message["subject"])

    def test_partial_wording_names_the_seller(self):
        order, alice_f, _ = self.shared_order()
        self.mark_shipped(alice_f, shipped_at=timezone.now(), carrier="ZTO", tracking_number="ZTO-7")
        content_services.send_order_shipped(alice_f, whole_order=False)
        message = self.sent()
        self.assertEqual(message["subject"], f"Part of your order {order.order_number} has shipped")
        self.assertIn("Alice Studio", message["body"])
        self.assertIn("ZTO-7", message["body"])
        self.assertIn("separately", message["body"])

    def test_tracking_line_is_omitted_when_nothing_was_entered(self):
        _, f = self.single_seller_order()
        self.mark_shipped(f, shipped_at=timezone.now())
        content_services.send_order_shipped(f, whole_order=True)
        body = self.sent()["body"]
        self.assertNotIn("Carrier", body)
        self.assertNotIn("Tracking", body)

    def test_no_arrival_notification_is_promised(self):
        # A multi-seller order has no delivery-confirmation workflow, so no
        # shipment notice may promise a follow-up "it has arrived" message.
        _, single_f = self.single_seller_order()
        _, shared_f, _ = self.shared_order()
        content_services.send_order_shipped(single_f, whole_order=True)
        content_services.send_order_shipped(shared_f, whole_order=False)
        bodies = [call.kwargs["body"] for call in self.sender.send.call_args_list]
        self.assertEqual(len(bodies), 2)
        for body in bodies:
            self.assertNotIn("let you know", body)
            self.assertNotIn("arrives", body)


# ---------------------------------------------------------------------------
# Seller API contract
# ---------------------------------------------------------------------------

class SellerApiSafetyTests(FulfilmentSafetyFixtures, TestCase):
    def setUp(self):
        self.make_catalogue()
        self.alice_user = make_seller_user("alice.safety@test.example")
        self.bob_user = make_seller_user("bob.safety@test.example")
        self.alice.owner = self.alice_user
        self.alice.save(update_fields=["owner"])
        self.bob.owner = self.bob_user
        self.bob.save(update_fields=["owner"])
        self.client = APIClient()

    def patch_fulfilment(self, order, payload, user=None):
        self.client.force_authenticate(user=user or self.alice_user)
        return self.client.patch(f"/api/seller/orders/{order.uuid}/fulfilment/",
                                 data=payload, format="json")

    def post_delivered(self, order, user=None):
        self.client.force_authenticate(user=user or self.alice_user)
        return self.client.post(f"/api/seller/orders/{order.uuid}/delivered/", format="json")

    def test_dispatching_an_ineligible_order_returns_the_validation_error_shape(self):
        order, f = self.single_seller_order(status=OrderStatus.PENDING,
                                            payment_status=PaymentStatus.UNPAID)
        response = self.patch_fulfilment(order, {"status": FULFILLED, "carrier": "DHL"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Validation failed.")
        self.assertIn("status", response.data["errors"])
        self.assertEqual(self.snapshot(f), (UNFULFILLED, "", "", None))

    def test_tracking_only_update_on_an_ineligible_order_succeeds(self):
        order, f = self.single_seller_order(status=OrderStatus.PENDING,
                                            payment_status=PaymentStatus.UNPAID)
        response = self.patch_fulfilment(order, {"carrier": "DHL", "tracking_number": "DHL-2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.snapshot(f), (UNFULFILLED, "DHL", "DHL-2", None))

    def test_dispatching_an_eligible_order_succeeds(self):
        order, f = self.single_seller_order()
        response = self.patch_fulfilment(order, {"status": FULFILLED})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["fulfillment"]["status"], FULFILLED)

    def test_delivery_of_a_multi_seller_order_is_rejected(self):
        order, alice_f, bob_f = self.shared_order()
        for f in (alice_f, bob_f):
            self.mark_shipped(f, shipped_at=timezone.now())
        response = self.post_delivered(order)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.get(pk=order.pk).status, OrderStatus.CONFIRMED)

    def test_delivery_of_a_shipped_single_seller_order_succeeds_once(self):
        order, _ = self.single_seller_order(fulfilment_status=FULFILLED)
        with mock.patch(DELIVERED_NOTICE) as notice:
            with self.captureOnCommitCallbacks(execute=True):
                first = self.post_delivered(order)
            with self.captureOnCommitCallbacks(execute=True):
                second = self.post_delivered(order)
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(first.data["status"], OrderStatus.DELIVERED)
        notice.assert_called_once()

    def test_another_sellers_order_is_not_found_for_delivery(self):
        order, _ = self.single_seller_order(fulfilment_status=FULFILLED)
        response = self.post_delivered(order, user=self.bob_user)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Order.objects.get(pk=order.pk).status, OrderStatus.CONFIRMED)


# ---------------------------------------------------------------------------
# Concurrency -- two real connections
# ---------------------------------------------------------------------------

@skipUnless(connection.vendor == "postgresql", "row-lock waits are observed via pg_stat_activity")
class ConcurrencyTests(FulfilmentSafetyFixtures, TransactionTestCase):
    """Request A runs inside a transaction that stays open while request B
    starts. The test proves B is genuinely waiting on a row lock (PostgreSQL
    reports wait_event_type = 'Lock' for B's backend), then lets A commit
    and checks that B acted on A's committed state."""

    LOCK_WAIT_TIMEOUT = 10

    def setUp(self):
        self.make_catalogue()

    def wait_for_lock_wait(self, box):
        deadline = time.monotonic() + self.LOCK_WAIT_TIMEOUT
        while time.monotonic() < deadline:
            pid = box.get("pid")
            if pid is not None:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s",
                                   [pid])
                    row = cursor.fetchone()
                if row and row[0] == "Lock":
                    return True
            time.sleep(0.02)
        return False

    def race(self, first, second):
        errors, box = [], {}
        held, release = threading.Event(), threading.Event()

        def run_first():
            try:
                with transaction.atomic():
                    first()
                    held.set()
                    release.wait(self.LOCK_WAIT_TIMEOUT + 5)
            except Exception as exc:  # pragma: no cover - surfaced by the assertion below
                errors.append(exc)
                held.set()
            finally:
                connection.close()

        def run_second():
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    box["pid"] = cursor.fetchone()[0]
                second()
            except Exception as exc:  # pragma: no cover
                errors.append(exc)
            finally:
                connection.close()

        thread_a = threading.Thread(target=run_first)
        thread_a.start()
        self.assertTrue(held.wait(self.LOCK_WAIT_TIMEOUT), "request A never took its locks")
        thread_b = threading.Thread(target=run_second)
        thread_b.start()
        try:
            blocked = self.wait_for_lock_wait(box)
        finally:
            release.set()
            thread_a.join(self.LOCK_WAIT_TIMEOUT + 10)
            thread_b.join(self.LOCK_WAIT_TIMEOUT + 10)
        self.assertEqual(errors, [])
        self.assertTrue(blocked, "request B never waited on a row lock held by request A")

    def test_concurrent_first_shipments_notify_once(self):
        _, f = self.single_seller_order()
        copy_a = SellerFulfillment.objects.get(pk=f.pk)
        copy_b = SellerFulfillment.objects.get(pk=f.pk)
        with mock.patch(SHIPPED_NOTICE) as notice:
            self.race(
                lambda: services.update_seller_fulfillment(copy_a, acting_maker=self.alice,
                                                           status=FULFILLED),
                lambda: services.update_seller_fulfillment(copy_b, acting_maker=self.alice,
                                                           status=FULFILLED),
            )
        self.assertEqual(notice.call_count, 1)
        self.assertIsNotNone(copy_a.shipped_at)
        self.assertEqual(copy_b.shipped_at, copy_a.shipped_at)
        self.assertEqual(self.snapshot(f)[3], copy_a.shipped_at)

    def test_concurrent_delivery_confirmations_notify_once(self):
        order, _ = self.single_seller_order(fulfilment_status=FULFILLED)
        copy_a = Order.objects.get(pk=order.pk)
        copy_b = Order.objects.get(pk=order.pk)
        with mock.patch(DELIVERED_NOTICE) as notice:
            self.race(
                lambda: services.mark_order_delivered(copy_a, acting_maker=self.alice),
                lambda: services.mark_order_delivered(copy_b, acting_maker=self.alice),
            )
        self.assertEqual(notice.call_count, 1)
        self.assertEqual(Order.objects.get(pk=order.pk).status, OrderStatus.DELIVERED)

    def test_concurrent_sibling_shipments_keep_the_parent_aggregate_correct(self):
        order, alice_f, bob_f = self.shared_order()
        with mock.patch(SHIPPED_NOTICE):
            self.race(
                lambda: services.update_seller_fulfillment(alice_f, acting_maker=self.alice,
                                                           status=FULFILLED),
                lambda: services.update_seller_fulfillment(bob_f, acting_maker=self.bob,
                                                           status=FULFILLED),
            )
        self.assertEqual(Order.objects.get(pk=order.pk).fulfillment_status, FULFILLED)
