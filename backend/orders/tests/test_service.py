"""Category G/H/I/J/K/L/V: seller ownership, tracking isolation, shipped_at
determinism, parent-order aggregation, and idempotent fulfilment creation --
all exercised through orders.services, independent of any future API-layer
permissions (this is what makes it security-critical: the check must hold
even if a view/serializer bug ever let the wrong id through).
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from orders import services
from orders.models import FulfillmentStatus, Order, SellerFulfillment

from .factories import make_bare_order, make_category, make_maker, make_order_item, make_product


class SellerOwnershipTests(TestCase):
    def setUp(self):
        self.alice = make_maker("alice", "Alice")
        self.bob = make_maker("bob", "Bob")
        self.order = make_bare_order()
        self.alice_f = SellerFulfillment.objects.create(order=self.order, maker=self.alice)
        self.bob_f = SellerFulfillment.objects.create(order=self.order, maker=self.bob)

    def test_owner_can_update_their_own_fulfillment(self):
        updated = services.update_seller_fulfillment(
            self.alice_f, acting_maker=self.alice, carrier="DHL", tracking_number="A1")
        self.assertEqual(updated.carrier, "DHL")
        self.assertEqual(updated.tracking_number, "A1")

    def test_non_owner_is_rejected_even_with_a_real_fulfillment_id(self):
        with self.assertRaises(PermissionDenied):
            services.update_seller_fulfillment(
                self.bob_f, acting_maker=self.alice, carrier="STOLEN", tracking_number="X")
        self.bob_f.refresh_from_db()
        self.assertEqual(self.bob_f.carrier, "")
        self.assertEqual(self.bob_f.tracking_number, "")


class StatusValidationTests(TestCase):
    """`choices=` on the model field is display/form metadata only -- Django
    does not run full_clean() on save() -- so update_seller_fulfillment must
    reject an invalid status itself rather than trust a future API
    serializer to have already done so."""

    def setUp(self):
        self.alice = make_maker("alice", "Alice")
        self.bob = make_maker("bob", "Bob")
        self.order = make_bare_order()
        self.alice_f = SellerFulfillment.objects.create(order=self.order, maker=self.alice)
        self.bob_f = SellerFulfillment.objects.create(order=self.order, maker=self.bob)

    def test_valid_existing_status_is_accepted(self):
        updated = services.update_seller_fulfillment(
            self.alice_f, acting_maker=self.alice, status=FulfillmentStatus.FULFILLED)
        self.assertEqual(updated.status, FulfillmentStatus.FULFILLED)

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValidationError):
            services.update_seller_fulfillment(
                self.alice_f, acting_maker=self.alice, status="invalid-status")

    def test_rejection_leaves_fulfillment_status_unchanged(self):
        with self.assertRaises(ValidationError):
            services.update_seller_fulfillment(
                self.alice_f, acting_maker=self.alice, status="invalid-status")
        self.alice_f.refresh_from_db()
        self.assertEqual(self.alice_f.status, FulfillmentStatus.UNFULFILLED)

    def test_rejection_leaves_parent_order_status_unchanged(self):
        Order.objects.filter(pk=self.order.pk).update(
            fulfillment_status=FulfillmentStatus.UNFULFILLED)
        with self.assertRaises(ValidationError):
            services.update_seller_fulfillment(
                self.alice_f, acting_maker=self.alice, status="invalid-status")
        self.order.refresh_from_db()
        self.assertEqual(self.order.fulfillment_status, FulfillmentStatus.UNFULFILLED)

    def test_rejection_leaves_shipped_at_unchanged(self):
        self.assertIsNone(self.alice_f.shipped_at)
        with self.assertRaises(ValidationError):
            services.update_seller_fulfillment(
                self.alice_f, acting_maker=self.alice, status="invalid-status")
        self.alice_f.refresh_from_db()
        self.assertIsNone(self.alice_f.shipped_at)

    def test_rejection_also_leaves_carrier_and_tracking_untouched(self):
        """An invalid status must not fall through to partially apply the
        other fields passed in the same call."""
        with self.assertRaises(ValidationError):
            services.update_seller_fulfillment(
                self.alice_f, acting_maker=self.alice, status="invalid-status",
                carrier="DHL", tracking_number="A1")
        self.alice_f.refresh_from_db()
        self.assertEqual(self.alice_f.carrier, "")
        self.assertEqual(self.alice_f.tracking_number, "")

    def test_ownership_check_still_takes_precedence_over_status_validation(self):
        """Seller-ownership protection (Category G) must still hold even when
        an invalid status is passed at the same time -- the wrong-seller
        check is not accidentally bypassed by the new validation path."""
        with self.assertRaises(PermissionDenied):
            services.update_seller_fulfillment(
                self.bob_f, acting_maker=self.alice, status="invalid-status")
        self.bob_f.refresh_from_db()
        self.assertEqual(self.bob_f.status, FulfillmentStatus.UNFULFILLED)


class SellerTrackingIsolationTests(TestCase):
    def setUp(self):
        self.alice = make_maker("alice", "Alice")
        self.bob = make_maker("bob", "Bob")
        self.order = make_bare_order()
        self.alice_f = SellerFulfillment.objects.create(order=self.order, maker=self.alice)
        self.bob_f = SellerFulfillment.objects.create(order=self.order, maker=self.bob)

    def test_updates_stay_isolated_per_seller(self):
        services.update_seller_fulfillment(self.alice_f, acting_maker=self.alice,
                                           carrier="DHL", tracking_number="ALICE123")
        self.bob_f.refresh_from_db()
        self.assertEqual(self.bob_f.carrier, "")
        self.assertEqual(self.bob_f.tracking_number, "")

        services.update_seller_fulfillment(self.bob_f, acting_maker=self.bob,
                                           carrier="FedEx", tracking_number="BOB456")
        self.alice_f.refresh_from_db()
        self.bob_f.refresh_from_db()
        self.assertEqual(self.alice_f.carrier, "DHL")
        self.assertEqual(self.alice_f.tracking_number, "ALICE123")
        self.assertEqual(self.bob_f.carrier, "FedEx")
        self.assertEqual(self.bob_f.tracking_number, "BOB456")


class ShippedAtTests(TestCase):
    def setUp(self):
        self.alice = make_maker("alice", "Alice")
        self.order = make_bare_order()
        self.fulfillment = SellerFulfillment.objects.create(order=self.order, maker=self.alice)

    def test_null_on_creation(self):
        self.assertIsNone(self.fulfillment.shipped_at)

    def test_set_on_first_transition_to_fulfilled(self):
        updated = services.update_seller_fulfillment(
            self.fulfillment, acting_maker=self.alice, status=FulfillmentStatus.FULFILLED)
        self.assertIsNotNone(updated.shipped_at)

    def test_unrelated_updates_do_not_change_shipped_at(self):
        services.update_seller_fulfillment(
            self.fulfillment, acting_maker=self.alice, status=FulfillmentStatus.FULFILLED)
        self.fulfillment.refresh_from_db()
        first_shipped_at = self.fulfillment.shipped_at

        services.update_seller_fulfillment(self.fulfillment, acting_maker=self.alice, carrier="DHL")
        self.fulfillment.refresh_from_db()
        self.assertEqual(self.fulfillment.shipped_at, first_shipped_at)

    def test_repeated_fulfilled_transition_does_not_regenerate_timestamp(self):
        services.update_seller_fulfillment(
            self.fulfillment, acting_maker=self.alice, status=FulfillmentStatus.FULFILLED)
        self.fulfillment.refresh_from_db()
        first_shipped_at = self.fulfillment.shipped_at

        services.update_seller_fulfillment(
            self.fulfillment, acting_maker=self.alice, status=FulfillmentStatus.FULFILLED)
        self.fulfillment.refresh_from_db()
        self.assertEqual(self.fulfillment.shipped_at, first_shipped_at)


class ParentOrderAggregationTests(TestCase):
    def setUp(self):
        self.alice = make_maker("alice", "Alice")
        self.bob = make_maker("bob", "Bob")
        self.order = make_bare_order()
        self.alice_f = SellerFulfillment.objects.create(order=self.order, maker=self.alice)
        self.bob_f = SellerFulfillment.objects.create(order=self.order, maker=self.bob)

    def test_all_unfulfilled_is_unfulfilled(self):
        services.sync_order_fulfillment_status(self.order)
        self.order.refresh_from_db()
        self.assertEqual(self.order.fulfillment_status, FulfillmentStatus.UNFULFILLED)

    def test_mixed_statuses_are_partial(self):
        services.update_seller_fulfillment(self.alice_f, acting_maker=self.alice,
                                           status=FulfillmentStatus.FULFILLED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.fulfillment_status, FulfillmentStatus.PARTIAL)

    def test_all_fulfilled_is_fulfilled(self):
        services.update_seller_fulfillment(self.alice_f, acting_maker=self.alice,
                                           status=FulfillmentStatus.FULFILLED)
        services.update_seller_fulfillment(self.bob_f, acting_maker=self.bob,
                                           status=FulfillmentStatus.FULFILLED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.fulfillment_status, FulfillmentStatus.FULFILLED)


class ThreeSellerAggregationTests(TestCase):
    """The aggregation rule must generalise past exactly two sellers."""

    def setUp(self):
        self.order = make_bare_order()
        self.makers = {name: make_maker(name, name.title())
                       for name in ("alice", "bob", "charlie")}
        self.fulfillments = {
            name: SellerFulfillment.objects.create(order=self.order, maker=maker)
            for name, maker in self.makers.items()
        }

    def _mark_fulfilled(self, name):
        services.update_seller_fulfillment(
            self.fulfillments[name], acting_maker=self.makers[name],
            status=FulfillmentStatus.FULFILLED)

    def test_two_of_three_fulfilled_is_partial(self):
        self._mark_fulfilled("alice")
        self._mark_fulfilled("bob")
        self.order.refresh_from_db()
        self.assertEqual(self.order.fulfillment_status, FulfillmentStatus.PARTIAL)

    def test_all_three_fulfilled_is_fulfilled(self):
        self._mark_fulfilled("alice")
        self._mark_fulfilled("bob")
        self._mark_fulfilled("charlie")
        self.order.refresh_from_db()
        self.assertEqual(self.order.fulfillment_status, FulfillmentStatus.FULFILLED)


class ParentCarrierCompatibilityTests(TestCase):
    def test_seller_level_updates_never_overwrite_the_legacy_parent_fields(self):
        order = make_bare_order()
        order.carrier = "LEGACY-CARRIER"
        order.tracking_number = "LEGACY-TRACK"
        order.save(update_fields=["carrier", "tracking_number"])

        alice = make_maker("alice", "Alice")
        bob = make_maker("bob", "Bob")
        alice_f = SellerFulfillment.objects.create(order=order, maker=alice)
        bob_f = SellerFulfillment.objects.create(order=order, maker=bob)

        services.update_seller_fulfillment(alice_f, acting_maker=alice,
                                           carrier="DHL", tracking_number="ALICE1")
        services.update_seller_fulfillment(bob_f, acting_maker=bob,
                                           carrier="FedEx", tracking_number="BOB1")

        order.refresh_from_db()
        self.assertEqual(order.carrier, "LEGACY-CARRIER")
        self.assertEqual(order.tracking_number, "LEGACY-TRACK")


class NoDuplicateCreationTests(TestCase):
    def test_create_seller_fulfillments_is_idempotent(self):
        category = make_category()
        alice = make_maker("alice", "Alice")
        product = make_product(maker=alice, category=category, slug="alice-mug")
        order = make_bare_order()
        make_order_item(order=order, product=product)

        first = services.create_seller_fulfillments(order)
        second = services.create_seller_fulfillments(order)

        self.assertEqual(len(first), 1)
        self.assertEqual([f.pk for f in first], [f.pk for f in second])
        self.assertEqual(SellerFulfillment.objects.filter(order=order, maker=alice).count(), 1)
