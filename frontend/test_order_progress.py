"""Buyer progress must follow seller fulfilment without changing commerce state."""
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from frontend.order_progress import buyer_order_progress
from orders.models import (
    FulfillmentStatus, Order, OrderItem, OrderStatus, PaymentStatus, SellerFulfillment,
)
from orders.services import update_seller_fulfillment
from orders.tests.factories import (
    make_bare_order, make_category, make_maker, make_order_item, make_product,
)

FULFILLED, PARTIAL, UNFULFILLED = (
    FulfillmentStatus.FULFILLED, FulfillmentStatus.PARTIAL, FulfillmentStatus.UNFULFILLED)
SHIPPED_ON = datetime(2026, 3, 9, 10, 0, tzinfo=dt_timezone.utc)
LATER_SHIPPED_ON = datetime(2026, 3, 11, 8, 0, tzinfo=dt_timezone.utc)
DISPATCHED, DELIVERED_STEP = 3, 4  # positions in the five-step timeline


class ProgressFixtures:
    def make_catalogue(self):
        category = make_category()
        self.alice = make_maker("alice-progress", "Alice")
        self.bob = make_maker("bob-progress", "Bob")
        self.a_product = make_product(maker=self.alice, category=category, slug="a-progress")
        self.b_product = make_product(maker=self.bob, category=category, slug="b-progress")

    def make_order(self, *, makers=("alice",), status=OrderStatus.CONFIRMED,
                   payment_status=PaymentStatus.PAID, user=None):
        order = make_bare_order(status=status, payment_status=payment_status)
        if user is not None:
            order.user = user
            order.save(update_fields=["user"])
        fulfilments = {}
        for name in makers:
            maker, product = ((self.alice, self.a_product) if name == "alice"
                              else (self.bob, self.b_product))
            make_order_item(order=order, product=product)
            fulfilments[name] = SellerFulfillment.objects.create(order=order, maker=maker)
        return order, fulfilments

    def ship(self, fulfilment, *, shipped_on=SHIPPED_ON, carrier="DHL", tracking_number="A123"):
        """Ship through the real service, then pin shipped_at for stable dates."""
        update_seller_fulfillment(fulfilment, acting_maker=fulfilment.maker, status=FULFILLED,
                                  carrier=carrier, tracking_number=tracking_number)
        SellerFulfillment.objects.filter(pk=fulfilment.pk).update(shipped_at=shipped_on)

    @staticmethod
    def progress(order, language="en"):
        order = (Order.objects.prefetch_related("items", "seller_fulfillments__maker")
                 .get(pk=order.pk))
        with translation.override(language):
            return buyer_order_progress(order)


class BuyerOrderProgressTests(ProgressFixtures, TestCase):
    def setUp(self):
        self.make_catalogue()

    def test_single_seller_dispatch_updates_buyer_progress(self):
        order, f = self.make_order()
        self.ship(f["alice"])
        result = self.progress(order)
        self.assertEqual(result["status"], OrderStatus.SHIPPED)
        self.assertEqual(result["label"], "On its way")
        self.assertTrue(result["timeline"][DISPATCHED]["done"])
        self.assertEqual(result["timeline"][DISPATCHED]["date"], "9 Mar")  # real shipped_at
        self.assertFalse(result["timeline"][DELIVERED_STEP]["done"])
        self.assertEqual(result["shipments"], [{
            "maker": "Alice", "dispatched": True, "date": "9 Mar",
            "carrier": "DHL", "tracking_number": "A123",
        }])
        # The presentation layer must never rewrite the commercial state.
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CONFIRMED)

    def test_one_of_two_sellers_does_not_mark_whole_order_shipped(self):
        order, f = self.make_order(makers=("alice", "bob"))
        self.ship(f["alice"])
        result = self.progress(order)
        self.assertEqual(result["status"], OrderStatus.CONFIRMED)
        self.assertEqual(result["label"], "Confirmed")
        self.assertFalse(result["timeline"][DISPATCHED]["done"])
        self.assertEqual([s["maker"] for s in result["shipments"]], ["Alice"])

    def test_all_sellers_fulfilled_completes_dispatch_on_the_last_shipment_date(self):
        order, f = self.make_order(makers=("alice", "bob"))
        self.ship(f["alice"], shipped_on=SHIPPED_ON)
        self.ship(f["bob"], shipped_on=LATER_SHIPPED_ON, carrier="SF", tracking_number="B9")
        result = self.progress(order)
        self.assertEqual(result["status"], OrderStatus.SHIPPED)
        self.assertEqual(result["timeline"][DISPATCHED]["date"], "11 Mar")
        self.assertEqual([(s["maker"], s["date"]) for s in result["shipments"]],
                         [("Alice", "9 Mar"), ("Bob", "11 Mar")])

    def test_partial_fulfilment_never_completes_dispatch(self):
        order, f = self.make_order()
        update_seller_fulfillment(f["alice"], acting_maker=self.alice, status=PARTIAL)
        result = self.progress(order)
        self.assertEqual(result["status"], OrderStatus.CONFIRMED)
        self.assertEqual(result["shipments"], [])  # nothing announced without tracking

        update_seller_fulfillment(f["alice"], acting_maker=self.alice, carrier="DHL",
                                  tracking_number="P1")
        result = self.progress(order)
        self.assertEqual(result["status"], OrderStatus.CONFIRMED)
        self.assertEqual(result["shipments"], [{
            "maker": "Alice", "dispatched": False, "date": "",
            "carrier": "DHL", "tracking_number": "P1",
        }])

    def test_backward_correction_removes_dispatched_progress(self):
        order, f = self.make_order()
        self.ship(f["alice"])
        update_seller_fulfillment(f["alice"], acting_maker=self.alice, status=UNFULFILLED)
        result = self.progress(order)
        self.assertEqual(result["label"], "Confirmed")
        self.assertFalse(result["timeline"][DISPATCHED]["done"])
        self.assertEqual(result["shipments"], [])

    def test_legacy_missing_seller_row_cannot_claim_complete_dispatch(self):
        order, f = self.make_order()
        make_order_item(order=order, product=self.b_product)  # Bob's line, no Bob fulfilment
        self.ship(f["alice"])
        result = self.progress(order)
        self.assertEqual(result["label"], "Confirmed")
        self.assertFalse(result["timeline"][DISPATCHED]["done"])
        self.assertEqual([s["maker"] for s in result["shipments"]], ["Alice"])  # still true

    def test_maker_less_line_cannot_claim_complete_dispatch(self):
        order, f = self.make_order()
        OrderItem.objects.create(order=order, product=None, maker=None, product_name="Old piece",
                                 unit_price=10, quantity=1, line_total=10)
        self.ship(f["alice"])
        self.assertEqual(self.progress(order)["status"], OrderStatus.CONFIRMED)

    def test_unpaid_record_does_not_gain_shipping_progress_from_stale_data(self):
        order, f = self.make_order(status=OrderStatus.PENDING, payment_status=PaymentStatus.UNPAID)
        SellerFulfillment.objects.filter(pk=f["alice"].pk).update(
            status=FULFILLED, shipped_at=SHIPPED_ON, tracking_number="STALE")
        result = self.progress(order)
        self.assertEqual(result["status"], OrderStatus.PENDING)
        self.assertEqual(result["label"], "Awaiting confirmation")
        self.assertEqual(result["shipments"], [])

    def test_stored_shipped_status_is_shown_as_stored(self):
        # The concierge flow sets Order.status = SHIPPED itself.
        order, f = self.make_order(status=OrderStatus.SHIPPED)
        self.assertEqual(self.progress(order)["label"], "On its way")
        # Fulfilments disagreeing with a stored status never downgrade it.
        self.ship(f["alice"])
        update_seller_fulfillment(f["alice"], acting_maker=self.alice, status=UNFULFILLED)
        result = self.progress(order)
        self.assertEqual(result["status"], OrderStatus.SHIPPED)
        self.assertEqual(result["label"], "On its way")

    def test_cancelled_order_keeps_terminal_state_and_shipment_history(self):
        order, f = self.make_order()
        self.ship(f["alice"])
        Order.objects.filter(pk=order.pk).update(status=OrderStatus.CANCELLED)
        result = self.progress(order)
        self.assertEqual(result["label"], "Cancelled")
        self.assertEqual(len(result["timeline"]), 2)
        self.assertEqual([s["tracking_number"] for s in result["shipments"]], ["A123"])

    def test_delivered_order_keeps_tracking_history_and_dispatch_date(self):
        order, f = self.make_order()
        self.ship(f["alice"])
        Order.objects.filter(pk=order.pk).update(status=OrderStatus.DELIVERED)
        result = self.progress(order)
        self.assertEqual(result["label"], "Delivered")
        self.assertTrue(result["timeline"][DELIVERED_STEP]["done"])
        self.assertEqual(result["timeline"][DISPATCHED]["date"], "9 Mar")
        self.assertEqual([s["tracking_number"] for s in result["shipments"]], ["A123"])

    def test_refund_after_shipment_keeps_history_without_promotion(self):
        order, f = self.make_order()
        self.ship(f["alice"])
        Order.objects.filter(pk=order.pk).update(payment_status=PaymentStatus.REFUNDED)
        result = self.progress(order)
        self.assertEqual(result["status"], OrderStatus.CONFIRMED)
        self.assertEqual([s["tracking_number"] for s in result["shipments"]], ["A123"])

    def test_chinese_labels_and_dates_use_the_existing_translations(self):
        order, f = self.make_order()
        self.ship(f["alice"])
        result = self.progress(order, language="zh-hans")
        self.assertEqual(result["label"], "运输途中")
        self.assertEqual(result["timeline"][DISPATCHED]["label"], "已发货")
        self.assertEqual(result["timeline"][DISPATCHED]["date"], "3月9日")
        self.assertEqual(result["shipments"][0]["date"], "3月9日")

    def test_progress_is_read_only_and_uses_prefetched_data(self):
        order, f = self.make_order(makers=("alice", "bob"))
        self.ship(f["alice"])
        loaded = (Order.objects.prefetch_related("items", "seller_fulfillments__maker")
                  .get(pk=order.pk))
        with CaptureQueriesContext(connection) as queries, translation.override("en"):
            buyer_order_progress(loaded)
        self.assertEqual(len(queries.captured_queries), 0)

    def test_unsaved_order_shows_its_stored_status(self):
        with translation.override("en"):
            result = buyer_order_progress(Order(order_number="AF-DRAFT", status=OrderStatus.CONFIRMED))
        self.assertEqual((result["status"], result["label"], result["shipments"]),
                         (OrderStatus.CONFIRMED, "Confirmed", []))


class TimelineDateIntegrityTests(ProgressFixtures, TestCase):
    """Completed milestones show only dates that were actually recorded."""

    PLACED_ON = datetime(2026, 3, 2, 9, 0, tzinfo=dt_timezone.utc)

    def setUp(self):
        self.make_catalogue()

    def make_order(self, **kwargs):
        order, fulfilments = super().make_order(**kwargs)
        Order.objects.filter(pk=order.pk).update(placed_at=self.PLACED_ON)
        return order, fulfilments

    @staticmethod
    def steps(result):
        return [(step["label"], step["done"], step["date"]) for step in result["timeline"]]

    def test_dispatch_shows_the_real_ship_date_and_packing_no_placement_date(self):
        order, f = self.make_order()
        self.ship(f["alice"])  # shipped 9 March
        self.assertEqual(self.steps(self.progress(order)), [
            ("Order placed", True, "2 Mar"), ("Confirmed", True, "2 Mar"),
            ("Made & packed", True, ""), ("Dispatched", True, "9 Mar"),
            ("Delivered", False, "Expected"),
        ])
        self.assertEqual(self.steps(self.progress(order, language="zh-hans")), [
            ("下单成功", True, "3月2日"), ("已确认", True, "3月2日"),
            ("制作及包装完成", True, ""), ("已发货", True, "3月9日"),
            ("已送达", False, "预计"),
        ])

    def test_missing_ship_timestamp_leaves_dispatch_undated(self):
        order, f = self.make_order()
        SellerFulfillment.objects.filter(pk=f["alice"].pk).update(status=FULFILLED, shipped_at=None)
        result = self.progress(order)
        self.assertEqual(result["status"], OrderStatus.SHIPPED)
        self.assertEqual(result["timeline"][DISPATCHED], {"label": "Dispatched", "done": True, "date": ""})
        self.assertEqual(result["shipments"][0]["date"], "")

    def test_multi_seller_dispatch_date_needs_every_sellers_ship_date(self):
        order, f = self.make_order(makers=("alice", "bob"))
        self.ship(f["alice"], shipped_on=SHIPPED_ON)
        self.ship(f["bob"], shipped_on=LATER_SHIPPED_ON)
        self.assertEqual(self.progress(order)["timeline"][DISPATCHED]["date"], "11 Mar")  # the latest

        SellerFulfillment.objects.filter(pk=f["bob"].pk).update(shipped_at=None)
        result = self.progress(order)
        self.assertEqual(result["status"], OrderStatus.SHIPPED)
        self.assertEqual(result["timeline"][DISPATCHED]["date"], "")
        self.assertEqual([s["date"] for s in result["shipments"]], ["9 Mar", ""])

    def test_stored_shipped_orders_keep_their_status_without_invented_dates(self):
        legacy = make_bare_order(status=OrderStatus.SHIPPED, payment_status=PaymentStatus.PAID)
        Order.objects.filter(pk=legacy.pk).update(placed_at=self.PLACED_ON)
        result = self.progress(legacy)  # no items, no fulfilment rows
        self.assertEqual((result["status"], result["label"]), (OrderStatus.SHIPPED, "On its way"))
        self.assertEqual(self.steps(result)[2:4],
                         [("Made & packed", True, ""), ("Dispatched", True, "")])
        self.assertEqual(self.steps(result)[0], ("Order placed", True, "2 Mar"))

        concierge, f = self.make_order(status=OrderStatus.SHIPPED)
        self.ship(f["alice"])
        self.assertEqual(self.progress(concierge)["timeline"][DISPATCHED]["date"], "9 Mar")

    def test_delivered_order_has_no_invented_delivery_date(self):
        order, f = self.make_order()
        self.ship(f["alice"])
        Order.objects.filter(pk=order.pk).update(status=OrderStatus.DELIVERED)
        self.assertEqual(self.steps(self.progress(order))[3:],
                         [("Dispatched", True, "9 Mar"), ("Delivered", True, "")])

    def test_progress_calculation_changes_no_stored_data(self):
        order, f = self.make_order(makers=("alice", "bob"))
        self.ship(f["alice"])

        def stored():
            return (list(Order.objects.filter(pk=order.pk).values()),
                    list(SellerFulfillment.objects.filter(order=order).order_by("pk").values()))

        before = stored()
        with CaptureQueriesContext(connection) as queries:
            for language in ("en", "zh-hans"):
                self.progress(order, language=language)
        writes = [q["sql"] for q in queries.captured_queries
                  if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
        self.assertEqual(writes, [])
        self.assertEqual(stored(), before)


@override_settings(
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class BuyerOrderPagesTests(ProgressFixtures, TestCase):
    """Rendered buyer pages agree with one another, in English and Chinese."""

    def setUp(self):
        self.make_catalogue()
        self.buyer = get_user_model().objects.create_user(
            email="progress.buyer@example.com", password="Buyer-pass-2026!")
        self.client.force_login(self.buyer)

    def pages(self, order, language):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
        return {
            "detail": self.client.get(reverse("account_order_detail", args=[order.order_number])),
            "list": self.client.get(reverse("account_orders")),
            "overview": self.client.get(reverse("account_overview")),
        }

    def test_fully_dispatched_order_reads_the_same_on_every_page(self):
        order, f = self.make_order(user=self.buyer)
        self.ship(f["alice"])
        for language, label, tracking in (("en", "On its way", "DHL · Tracking A123"),
                                          ("zh-hans", "运输途中", "DHL · 运单号 A123")):
            with self.subTest(language=language):
                pages = self.pages(order, language)
                for name, response in pages.items():
                    self.assertEqual(response.status_code, 200, name)
                    self.assertContains(response, f'class="status status--shipped">{label}</span>')
                detail = pages["detail"]
                self.assertContains(detail, tracking)
                self.assertContains(detail, "9 Mar" if language == "en" else "3月9日")
                self.assertContains(detail, f"{label}</p>")  # the page lede agrees too
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CONFIRMED)

    def test_partly_dispatched_order_stays_confirmed_and_names_only_the_shipped_seller(self):
        order, f = self.make_order(makers=("alice", "bob"), user=self.buyer)
        self.ship(f["alice"], carrier="", tracking_number="TRK-1")
        pages = self.pages(order, "en")
        for name, response in pages.items():
            self.assertContains(response, 'class="status status--confirmed">Confirmed</span>')
        detail = pages["detail"]
        self.assertContains(detail, "Alice · Dispatched 9 Mar · TRK-1")
        self.assertNotContains(detail, "Bob · Dispatched")
        self.assertNotContains(detail, " ·  · ")  # no empty carrier separator

    def test_order_list_queries_do_not_grow_with_the_number_of_orders(self):
        def list_queries():
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(reverse("account_orders")).status_code, 200)
            return len(queries.captured_queries)

        order, f = self.make_order(makers=("alice", "bob"), user=self.buyer)
        self.ship(f["alice"])
        one_order = list_queries()
        for _ in range(3):
            more, g = self.make_order(makers=("alice", "bob"), user=self.buyer)
            self.ship(g["bob"])
        self.assertEqual(list_queries(), one_order)
