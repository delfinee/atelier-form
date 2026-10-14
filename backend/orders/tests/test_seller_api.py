"""API-layer tests for Yi Jun's seller order and fulfilment endpoints.

These tests hit the actual HTTP endpoints (GET and PATCH) through Django's
test client, which means they exercise the full stack: URL routing → ViewSet
→ serializer → service → database, and back.

Samuel's service-layer tests (test_service.py) already prove the database
logic is correct. These tests prove that the API correctly exposes that logic
to the outside world and guards it properly.

Test categories
---------------
A – Read: seller sees only their own orders and items
B – Read: seller sees their own fulfilment data, not another seller's
C – Write: seller can update carrier, tracking, status via PATCH
D – Security: wrong seller, non-seller, and unauthenticated users are blocked
E – Validation: bad input is rejected before touching the database
"""

from django.test import TestCase
from rest_framework.test import APIClient

from orders.models import FulfillmentStatus, OrderStatus, PaymentStatus, SellerFulfillment

from .factories import (
    make_bare_order,
    make_buyer,
    make_category,
    make_maker,
    make_order_item,
    make_product,
    make_seller_user,
)


# ---------------------------------------------------------------------------
# Shared setup helper
# ---------------------------------------------------------------------------

class SellerAPIBase(TestCase):
    """Sets up two sellers, one buyer, one shared order, and their products.

    Order layout
    ------------
    - alice_item : 2 × Alice's Mug  (¥20 each → ¥40)
    - bob_item   : 1 × Bob's Chair  (¥30 each → ¥30)

    Alice's SellerFulfillment and Bob's SellerFulfillment are created and
    attached to the same order, mimicking what services.create_order() does
    at real checkout time.

    `shared_order_fields` lets a subclass set the shared order's status and
    payment_status; by default it is a freshly placed, unpaid order.
    """

    shared_order_fields = {}

    def setUp(self):
        category = make_category()

        # Seller accounts with maker profiles linked by `owner`
        self.alice_user = make_seller_user("alice@test.example", first_name="Alice")
        self.alice_maker = make_maker("alice-studio", "Alice's Studio",
                                     owner=self.alice_user)

        self.bob_user = make_seller_user("bob@test.example", first_name="Bob")
        self.bob_maker = make_maker("bob-workshop", "Bob's Workshop",
                                   owner=self.bob_user)

        # A plain buyer account (no maker profile, is_seller=False by default)
        self.buyer_user = make_buyer("buyer@test.example")

        # Products
        self.alice_product = make_product(maker=self.alice_maker, category=category,
                                          slug="alice-mug", name="Alice's Mug", price="20.00")
        self.bob_product = make_product(maker=self.bob_maker, category=category,
                                        slug="bob-chair", name="Bob's Chair", price="30.00")

        # One shared order containing items from BOTH sellers
        self.order = make_bare_order(**self.shared_order_fields)
        self.alice_item = make_order_item(order=self.order, product=self.alice_product,
                                          quantity=2)
        self.bob_item = make_order_item(order=self.order, product=self.bob_product,
                                        quantity=1)

        # Per-seller fulfilment records (created automatically at checkout in prod)
        self.alice_fulfillment = SellerFulfillment.objects.create(
            order=self.order, maker=self.alice_maker)
        self.bob_fulfillment = SellerFulfillment.objects.create(
            order=self.order, maker=self.bob_maker)

        # An order that contains ONLY Bob's items (Alice must not see this)
        self.bob_only_order = make_bare_order(email="buyer2@test.example")
        make_order_item(order=self.bob_only_order, product=self.bob_product)
        SellerFulfillment.objects.create(order=self.bob_only_order, maker=self.bob_maker)

        # An order that contains ONLY Alice's items (Bob must not see or update this)
        self.alice_only_order = make_bare_order(email="buyer3@test.example")
        make_order_item(order=self.alice_only_order, product=self.alice_product)
        SellerFulfillment.objects.create(order=self.alice_only_order, maker=self.alice_maker)

        self.client = APIClient()

    def login_as(self, user):
        self.client.force_authenticate(user=user)


# ---------------------------------------------------------------------------
# Category A – Read: order list and detail isolation
# ---------------------------------------------------------------------------

class SellerOrderListTests(SellerAPIBase):
    """A seller's order list only contains orders with their own items."""

    def test_alice_sees_shared_order_in_list(self):
        """The shared order has Alice's items so she should see it."""
        self.login_as(self.alice_user)
        response = self.client.get("/api/seller/orders/")
        self.assertEqual(response.status_code, 200)
        items = response.data.get("items", response.data.get("results", []))
        uuids = [o["uuid"] for o in items]
        self.assertIn(str(self.order.uuid), uuids)

    def test_alice_does_not_see_bob_only_order(self):
        """An order with no Alice items must be invisible to Alice."""
        self.login_as(self.alice_user)
        response = self.client.get("/api/seller/orders/")
        self.assertEqual(response.status_code, 200)
        items = response.data.get("items", response.data.get("results", []))
        uuids = [o["uuid"] for o in items]
        self.assertNotIn(str(self.bob_only_order.uuid), uuids)

    def test_unauthenticated_user_cannot_list(self):
        """No login, no access."""
        response = self.client.get("/api/seller/orders/")
        self.assertIn(response.status_code, [401, 403])

    def test_buyer_cannot_list(self):
        """Regular buyer accounts do not have seller access."""
        self.login_as(self.buyer_user)
        response = self.client.get("/api/seller/orders/")
        self.assertEqual(response.status_code, 403)


class SellerOrderDetailTests(SellerAPIBase):
    """A seller's order detail shows only their items and their fulfilment."""

    def _get_order(self, uuid):
        return self.client.get(f"/api/seller/orders/{uuid}/")

    def test_alice_retrieves_shared_order(self):
        """Alice can fetch the order detail because it has her items."""
        self.login_as(self.alice_user)
        response = self._get_order(self.order.uuid)
        self.assertEqual(response.status_code, 200)

    def test_alice_only_sees_her_items(self):
        """Items list must contain only Alice's Mug, not Bob's Chair."""
        self.login_as(self.alice_user)
        response = self._get_order(self.order.uuid)
        item_names = [i["product_name"] for i in response.data["items"]]
        self.assertIn("Alice's Mug", item_names)
        self.assertNotIn("Bob's Chair", item_names)

    def test_alice_seller_subtotal_is_only_her_lines(self):
        """seller_subtotal = 2 × ¥20 = ¥40, not the full order total."""
        self.login_as(self.alice_user)
        response = self._get_order(self.order.uuid)
        self.assertEqual(float(response.data["seller_subtotal"]), 40.00)

    def test_alice_cannot_retrieve_bob_only_order(self):
        """An order with no Alice items returns 404, not 403.
        This hides the existence of the order from Alice entirely."""
        self.login_as(self.alice_user)
        response = self._get_order(self.bob_only_order.uuid)
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# Category B – Read: fulfilment data is seller-specific
# ---------------------------------------------------------------------------

class SellerFulfilmentReadTests(SellerAPIBase):
    """Each seller sees their own fulfilment record, not another seller's."""

    def setUp(self):
        super().setUp()
        # Pre-fill Bob's fulfilment with a carrier so we can prove Alice
        # does NOT see it on her copy of the same order.
        self.bob_fulfillment.carrier = "FedEx"
        self.bob_fulfillment.tracking_number = "FX-BOB-999"
        self.bob_fulfillment.status = FulfillmentStatus.FULFILLED
        self.bob_fulfillment.save()

    def test_alice_sees_her_own_carrier(self):
        self.login_as(self.alice_user)
        response = self.client.get(f"/api/seller/orders/{self.order.uuid}/")
        self.assertEqual(response.status_code, 200)
        # Alice's carrier is blank, NOT FedEx
        self.assertEqual(response.data["carrier"], "")

    def test_alice_does_not_see_bob_tracking_number(self):
        self.login_as(self.alice_user)
        response = self.client.get(f"/api/seller/orders/{self.order.uuid}/")
        self.assertNotEqual(response.data["tracking_number"], "FX-BOB-999")

    def test_alice_sees_unfulfilled_status_not_bob_fulfilled(self):
        self.login_as(self.alice_user)
        response = self.client.get(f"/api/seller/orders/{self.order.uuid}/")
        self.assertEqual(response.data["fulfillment_status"],
                         FulfillmentStatus.UNFULFILLED)

    def test_fulfillment_object_is_present_in_response(self):
        self.login_as(self.alice_user)
        response = self.client.get(f"/api/seller/orders/{self.order.uuid}/")
        self.assertIn("fulfillment", response.data)
        self.assertIsNotNone(response.data["fulfillment"])


# ---------------------------------------------------------------------------
# Category C – Write: PATCH /api/seller/orders/{uuid}/fulfilment/
# ---------------------------------------------------------------------------

class SellerFulfilmentUpdateTests(SellerAPIBase):
    """Alice can update her own carrier, tracking number, and status."""

    # Paid and confirmed: these tests include a successful dispatch.
    shared_order_fields = {"status": OrderStatus.CONFIRMED, "payment_status": PaymentStatus.PAID}

    def _patch(self, uuid, payload):
        return self.client.patch(
            f"/api/seller/orders/{uuid}/fulfilment/",
            data=payload,
            format="json",
        )

    def test_alice_can_update_carrier_and_tracking(self):
        self.login_as(self.alice_user)
        response = self._patch(self.order.uuid, {
            "carrier": "SF Express",
            "tracking_number": "SF123456789",
        })
        self.assertEqual(response.status_code, 200)
        self.alice_fulfillment.refresh_from_db()
        self.assertEqual(self.alice_fulfillment.carrier, "SF Express")
        self.assertEqual(self.alice_fulfillment.tracking_number, "SF123456789")

    def test_alice_marking_fulfilled_sets_shipped_at(self):
        """Samuel's service sets shipped_at when status first becomes FULFILLED."""
        self.login_as(self.alice_user)
        self.assertIsNone(self.alice_fulfillment.shipped_at)
        response = self._patch(self.order.uuid, {"status": FulfillmentStatus.FULFILLED})
        self.assertEqual(response.status_code, 200)
        self.alice_fulfillment.refresh_from_db()
        self.assertIsNotNone(self.alice_fulfillment.shipped_at)

    def test_alice_update_does_not_change_bob_fulfillment(self):
        """Updating Alice's record must leave Bob's untouched."""
        self.login_as(self.alice_user)
        self._patch(self.order.uuid, {"carrier": "SF Express"})
        self.bob_fulfillment.refresh_from_db()
        self.assertEqual(self.bob_fulfillment.carrier, "")

    def test_partial_update_only_changes_provided_fields(self):
        """PATCH with only carrier must leave tracking_number unchanged."""
        self.alice_fulfillment.tracking_number = "EXISTING-TRACK"
        self.alice_fulfillment.save()
        self.login_as(self.alice_user)
        self._patch(self.order.uuid, {"carrier": "DHL"})
        self.alice_fulfillment.refresh_from_db()
        self.assertEqual(self.alice_fulfillment.tracking_number, "EXISTING-TRACK")

    def test_updated_values_appear_in_response(self):
        """The response body immediately reflects the new values."""
        self.login_as(self.alice_user)
        response = self._patch(self.order.uuid, {
            "carrier": "ZTO",
            "tracking_number": "ZTO-999",
        })
        self.assertEqual(response.data["carrier"], "ZTO")
        self.assertEqual(response.data["tracking_number"], "ZTO-999")


# ---------------------------------------------------------------------------
# Category D – Security: wrong seller, non-seller, and anonymous
# ---------------------------------------------------------------------------

class SellerFulfilmentSecurityTests(SellerAPIBase):
    """The update endpoint blocks anyone who is not the correct seller."""

    def _patch(self, uuid, payload, user=None):
        if user:
            self.client.force_authenticate(user=user)
        return self.client.patch(
            f"/api/seller/orders/{uuid}/fulfilment/",
            data=payload,
            format="json",
        )

    def test_bob_cannot_update_alice_only_order(self):
        """Bob sending a PATCH to an order containing only Alice's items gets 404."""
        response = self._patch(self.alice_only_order.uuid,
                               {"carrier": "DHL"}, user=self.bob_user)
        self.assertEqual(response.status_code, 404)

    def test_bob_update_on_shared_order_does_not_affect_alice(self):
        """On a shared order, Bob's update only affects Bob's fulfillment."""
        response = self._patch(self.order.uuid,
                               {"carrier": "DHL"}, user=self.bob_user)
        self.assertEqual(response.status_code, 200)
        self.alice_fulfillment.refresh_from_db()
        self.assertEqual(self.alice_fulfillment.carrier, "")

    def test_buyer_cannot_update_any_fulfilment(self):
        """Regular buyer has no seller access at all."""
        response = self._patch(self.order.uuid,
                               {"carrier": "DHL"}, user=self.buyer_user)
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_update_any_fulfilment(self):
        """No auth header → 401 or 403."""
        response = self.client.patch(
            f"/api/seller/orders/{self.order.uuid}/fulfilment/",
            data={"carrier": "DHL"},
            format="json",
        )
        self.assertIn(response.status_code, [401, 403])


# ---------------------------------------------------------------------------
# Category E – Validation: bad input is rejected
# ---------------------------------------------------------------------------

class SellerFulfilmentValidationTests(SellerAPIBase):
    """Invalid data is caught by the serializer before touching the database."""

    def _patch(self, payload):
        self.client.force_authenticate(user=self.alice_user)
        return self.client.patch(
            f"/api/seller/orders/{self.order.uuid}/fulfilment/",
            data=payload,
            format="json",
        )

    def test_invalid_status_returns_400(self):
        """Status values not in FulfillmentStatus are rejected."""
        response = self._patch({"status": "flying_through_clouds"})
        self.assertEqual(response.status_code, 400)

    def test_invalid_status_does_not_change_database(self):
        """A rejected request must not partially save anything."""
        self._patch({"status": "flying_through_clouds", "carrier": "SF Express"})
        self.alice_fulfillment.refresh_from_db()
        self.assertEqual(self.alice_fulfillment.carrier, "")

    def test_carrier_too_long_returns_400(self):
        """carrier is capped at 80 characters."""
        response = self._patch({"carrier": "X" * 81})
        self.assertEqual(response.status_code, 400)

    def test_empty_payload_is_accepted(self):
        """An empty PATCH is valid (nothing to update, no crash)."""
        response = self._patch({})
        self.assertEqual(response.status_code, 200)

