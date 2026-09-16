"""Category C/D/E/M/N/O/P/Q/R/S/X: SellerFulfillment creation through the real
checkout path (orders.services.create_order), plus regression coverage
proving existing checkout behaviour -- stock, cart clearing, OrderItem
snapshots, transactionality, payment state -- is unchanged by adding it.
"""
from unittest import mock

from django.test import TestCase

from orders import services
from orders.models import Cart, CartItem, Order, OrderItem, PaymentStatus, SellerFulfillment

from .factories import SHIPPING_ADDRESS, make_buyer, make_category, make_maker, make_product


class MultiSellerCheckoutTests(TestCase):
    """Category C: one Order, three OrderItems, exactly two SellerFulfillments
    -- never one fulfilment per OrderItem."""

    def setUp(self):
        category = make_category()
        self.alice = make_maker("alice", "Alice")
        self.bob = make_maker("bob", "Bob")
        self.alice_a = make_product(maker=self.alice, category=category, slug="alice-a", name="Alice A")
        self.alice_b = make_product(maker=self.alice, category=category, slug="alice-b", name="Alice B")
        self.bob_c = make_product(maker=self.bob, category=category, slug="bob-c", name="Bob C")
        self.buyer = make_buyer()
        self.cart = Cart.objects.create(user=self.buyer)
        CartItem.objects.create(cart=self.cart, product=self.alice_a, quantity=1)
        CartItem.objects.create(cart=self.cart, product=self.alice_b, quantity=1)
        CartItem.objects.create(cart=self.cart, product=self.bob_c, quantity=1)

    def _checkout(self):
        return services.create_order(cart=self.cart, email="buyer@example.test",
                                     shipping_address=SHIPPING_ADDRESS, user=self.buyer)

    def test_one_order_three_items_two_fulfillments(self):
        order = self._checkout()
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(order.items.count(), 3)
        fulfillments = SellerFulfillment.objects.filter(order=order)
        self.assertEqual(fulfillments.count(), 2)
        self.assertEqual(set(fulfillments.values_list("maker_id", flat=True)),
                         {self.alice.id, self.bob.id})

    def test_correct_item_membership_no_cross_seller_contamination(self):
        """Category E: Alice's fulfilment resolves only her lines, Bob's only his."""
        order = self._checkout()
        alice_f = SellerFulfillment.objects.get(order=order, maker=self.alice)
        bob_f = SellerFulfillment.objects.get(order=order, maker=self.bob)
        self.assertEqual(set(alice_f.items.values_list("product_slug", flat=True)),
                         {"alice-a", "alice-b"})
        self.assertEqual(set(bob_f.items.values_list("product_slug", flat=True)), {"bob-c"})


class SingleSellerCheckoutTests(TestCase):
    """Category D: multiple lines, one seller -> exactly one fulfilment."""

    def test_single_seller_multi_item_creates_one_fulfillment(self):
        category = make_category()
        alice = make_maker("alice", "Alice")
        product_a = make_product(maker=alice, category=category, slug="alice-a")
        product_b = make_product(maker=alice, category=category, slug="alice-b")
        buyer = make_buyer()
        cart = Cart.objects.create(user=buyer)
        CartItem.objects.create(cart=cart, product=product_a, quantity=1)
        CartItem.objects.create(cart=cart, product=product_b, quantity=1)

        order = services.create_order(cart=cart, email="buyer@example.test",
                                      shipping_address=SHIPPING_ADDRESS, user=buyer)
        self.assertEqual(SellerFulfillment.objects.filter(order=order).count(), 1)
        self.assertEqual(order.items.count(), 2)


class OrderIsolationTests(TestCase):
    """Category F: fulfilment item resolution requires (order, maker) together
    -- a second order for the same buyer and the same maker must not leak."""

    def test_fulfillment_for_one_order_never_resolves_another_orders_items(self):
        category = make_category()
        alice = make_maker("alice", "Alice")
        product = make_product(maker=alice, category=category, slug="alice-a", stock_quantity=100)
        buyer = make_buyer()

        cart1 = Cart.objects.create(user=buyer)
        CartItem.objects.create(cart=cart1, product=product, quantity=1)
        order1 = services.create_order(cart=cart1, email="buyer@example.test",
                                       shipping_address=SHIPPING_ADDRESS, user=buyer)

        cart2 = Cart.objects.create(user=buyer)
        CartItem.objects.create(cart=cart2, product=product, quantity=1)
        order2 = services.create_order(cart=cart2, email="buyer@example.test",
                                       shipping_address=SHIPPING_ADDRESS, user=buyer)

        f1 = SellerFulfillment.objects.get(order=order1, maker=alice)
        f2 = SellerFulfillment.objects.get(order=order2, maker=alice)
        self.assertEqual(f1.items.count(), 1)
        self.assertEqual(f2.items.count(), 1)
        self.assertNotIn(f1.items.get().pk, f2.items.values_list("pk", flat=True))


class OrderItemSnapshotRegressionTests(TestCase):
    """Category M: existing OrderItem seller snapshot fields are unaffected."""

    def test_maker_snapshot_fields_still_populated(self):
        category = make_category()
        alice = make_maker("alice", "Alice")
        product = make_product(maker=alice, category=category, slug="alice-a")
        buyer = make_buyer()
        cart = Cart.objects.create(user=buyer)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        order = services.create_order(cart=cart, email="buyer@example.test",
                                      shipping_address=SHIPPING_ADDRESS, user=buyer)
        item = order.items.get()
        self.assertEqual(item.maker, alice)
        self.assertEqual(item.maker_name, "Alice")


class InventoryRegressionTests(TestCase):
    """Category N: stock still decrements exactly as before."""

    def test_stock_decremented_exactly_as_before(self):
        category = make_category()
        alice = make_maker("alice", "Alice")
        product = make_product(maker=alice, category=category, slug="alice-a", stock_quantity=10)
        buyer = make_buyer()
        cart = Cart.objects.create(user=buyer)
        CartItem.objects.create(cart=cart, product=product, quantity=3)

        services.create_order(cart=cart, email="buyer@example.test",
                              shipping_address=SHIPPING_ADDRESS, user=buyer)
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 7)


class CartClearingRegressionTests(TestCase):
    """Category O: cart clearing/deactivation still happens after a successful
    checkout; fulfilment creation does not leave checkout half-completed."""

    def test_cart_cleared_and_deactivated_after_checkout(self):
        category = make_category()
        alice = make_maker("alice", "Alice")
        product = make_product(maker=alice, category=category, slug="alice-a")
        buyer = make_buyer()
        cart = Cart.objects.create(user=buyer)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        services.create_order(cart=cart, email="buyer@example.test",
                              shipping_address=SHIPPING_ADDRESS, user=buyer)
        cart.refresh_from_db()
        self.assertFalse(cart.items.exists())
        self.assertFalse(cart.is_active)


class PaymentRegressionTests(TestCase):
    """Category P: create_order() itself never touches payment state -- the
    payment session is created by orders.api.CheckoutView, outside this
    function's boundary, so nothing here is mocked beyond the checkout call
    itself. This just confirms adding SellerFulfillment left that boundary
    alone: the order remains one commercial UNPAID Order, not per-seller
    payment records."""

    def test_order_remains_unpaid_and_singular_after_checkout(self):
        category = make_category()
        alice = make_maker("alice", "Alice")
        product = make_product(maker=alice, category=category, slug="alice-a")
        buyer = make_buyer()
        cart = Cart.objects.create(user=buyer)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        order = services.create_order(cart=cart, email="buyer@example.test",
                                      shipping_address=SHIPPING_ADDRESS, user=buyer)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(order.payment_status, PaymentStatus.UNPAID)


class TransactionRollbackTests(TestCase):
    """Category Q: a failure inside fulfilment creation must roll back the
    whole checkout -- no Order, no OrderItems, no stock decrement, no cart
    mutation survives."""

    def test_fulfillment_creation_failure_rolls_back_entire_checkout(self):
        category = make_category()
        alice = make_maker("alice", "Alice")
        product = make_product(maker=alice, category=category, slug="alice-a", stock_quantity=10)
        buyer = make_buyer()
        cart = Cart.objects.create(user=buyer)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        with mock.patch("orders.services.create_seller_fulfillments",
                       side_effect=RuntimeError("forced failure")):
            with self.assertRaises(RuntimeError):
                services.create_order(cart=cart, email="buyer@example.test",
                                      shipping_address=SHIPPING_ADDRESS, user=buyer)

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(SellerFulfillment.objects.count(), 0)
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 10)
        cart.refresh_from_db()
        self.assertTrue(cart.items.exists())
        self.assertTrue(cart.is_active)


class DifferentOrdersReuseMakerTests(TestCase):
    """Category R: the same maker across two separate checkouts is allowed --
    uniqueness is per (order, maker), never a global per-maker lock."""

    def test_same_maker_across_two_orders_allowed(self):
        category = make_category()
        alice = make_maker("alice", "Alice")
        product = make_product(maker=alice, category=category, slug="alice-a", stock_quantity=100)
        buyer = make_buyer()

        for _ in range(2):
            cart = Cart.objects.create(user=buyer)
            CartItem.objects.create(cart=cart, product=product, quantity=1)
            services.create_order(cart=cart, email="buyer@example.test",
                                  shipping_address=SHIPPING_ADDRESS, user=buyer)

        self.assertEqual(SellerFulfillment.objects.filter(maker=alice).count(), 2)


class DifferentMakersSameOrderTests(TestCase):
    """Category S: two makers in one order both get their own fulfilment --
    the constraint must not make `order` globally unique."""

    def test_two_makers_one_order_allowed(self):
        category = make_category()
        alice = make_maker("alice", "Alice")
        bob = make_maker("bob", "Bob")
        product_a = make_product(maker=alice, category=category, slug="alice-a")
        product_b = make_product(maker=bob, category=category, slug="bob-b")
        buyer = make_buyer()
        cart = Cart.objects.create(user=buyer)
        CartItem.objects.create(cart=cart, product=product_a, quantity=1)
        CartItem.objects.create(cart=cart, product=product_b, quantity=1)

        order = services.create_order(cart=cart, email="buyer@example.test",
                                      shipping_address=SHIPPING_ADDRESS, user=buyer)
        self.assertEqual(SellerFulfillment.objects.filter(order=order).count(), 2)


class QueryGroupingSanityTests(TestCase):
    """Category X: fulfilment creation groups by distinct maker, not by line --
    100 lines from 3 makers must produce exactly 3 SellerFulfillment rows."""

    def test_grouping_is_by_distinct_maker_not_per_item(self):
        from .factories import make_bare_order, make_order_item

        category = make_category()
        makers = [make_maker(f"maker-{i}", f"Maker {i}") for i in range(3)]
        products = [make_product(maker=m, category=category, slug=f"p-{i}", name=f"P{i}")
                   for i, m in enumerate(makers)]
        order = make_bare_order()
        for i in range(100):
            make_order_item(order=order, product=products[i % 3])

        result = services.create_seller_fulfillments(order)
        self.assertEqual(len(result), 3)
        self.assertEqual(SellerFulfillment.objects.filter(order=order).count(), 3)
