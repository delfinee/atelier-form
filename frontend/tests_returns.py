"""Browser flow for returns: buyer request form and seller returns queue."""

from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from imagery.models import SiteImage
from orders.models import FulfillmentStatus, OrderStatus, PaymentStatus, ReturnRequest, ReturnStatus
from orders.services import create_seller_fulfillments
from orders.tests.factories import (
    make_bare_order, make_buyer, make_category, make_maker, make_order_item, make_product,
    make_seller_user,
)


def png_upload(name="damage.png"):
    buffer = BytesIO()
    Image.new("RGB", (40, 30), "red").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(
    STORAGES={
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class ReturnViewTests(TestCase):
    def setUp(self):
        category = make_category()
        self.alice_user = make_seller_user("alice@example.test")
        self.bob_user = make_seller_user("bob@example.test")
        self.alice = make_maker("alice", "Alice", owner=self.alice_user)
        self.bob = make_maker("bob", "Bob", owner=self.bob_user)
        self.buyer = make_buyer()
        mug = make_product(maker=self.alice, category=category, slug="mug", name="Mug", price="30.00")
        scarf = make_product(maker=self.bob, category=category, slug="scarf", name="Scarf", price="50.00")

        self.order = make_bare_order(status=OrderStatus.SHIPPED, payment_status=PaymentStatus.PAID)
        self.order.user = self.buyer
        self.order.save()
        self.item = make_order_item(order=self.order, product=mug, quantity=2)
        self.bob_item = make_order_item(order=self.order, product=scarf, quantity=1)
        create_seller_fulfillments(self.order)
        self.order.seller_fulfillments.filter(maker=self.alice).update(
            status=FulfillmentStatus.FULFILLED, shipped_at=timezone.now())
        self.order.fulfillment_status = FulfillmentStatus.PARTIAL
        self.order.save()

    def form_url(self, item=None):
        return reverse("account_return_request", args=[self.order.order_number, (item or self.item).pk])

    def make_return(self, **overrides):
        data = {"order": self.order, "order_item": self.item, "maker": self.alice,
                "buyer": self.buyer, "quantity": 1, "reason": "faulty"}
        data.update(overrides)
        return ReturnRequest.objects.create(**data)

    # -- buyer ---------------------------------------------------------------

    def test_order_page_links_to_return_form(self):
        self.client.force_login(self.buyer)
        response = self.client.get(reverse("account_order_detail", args=[self.order.order_number]))
        self.assertContains(response, self.form_url())

    def test_buyer_submits_a_return(self):
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get(self.form_url()).status_code, 200)
        response = self.client.post(self.form_url(), {"reason": "changed_mind", "quantity": 2,
                                                      "details": "Not my colour"})
        self.assertRedirects(response, reverse("account_order_detail", args=[self.order.order_number]))
        rr = ReturnRequest.objects.get()
        self.assertEqual((rr.maker, rr.quantity, rr.details), (self.alice, 2, "Not my colour"))
        page = self.client.get(reverse("account_order_detail", args=[self.order.order_number]))
        self.assertContains(page, "status--requested")

    def test_damage_report_stores_the_photo(self):
        self.client.force_login(self.buyer)
        response = self.client.post(self.form_url(), {"reason": "damaged", "quantity": 1,
                                                      "photo": png_upload()})
        self.assertEqual(response.status_code, 302)
        rr = ReturnRequest.objects.get()
        self.assertTrue(rr.photo.startswith("return-photo-"))
        self.assertTrue(SiteImage.objects.filter(name=rr.photo).exists())

    def test_damage_report_without_photo_shows_error_and_saves_nothing(self):
        self.client.force_login(self.buyer)
        response = self.client.post(self.form_url(), {"reason": "damaged", "quantity": 1})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add a photograph of the damage.")
        self.assertFalse(ReturnRequest.objects.exists())

    def test_quantity_above_what_was_bought_is_rejected(self):
        self.client.force_login(self.buyer)
        response = self.client.post(self.form_url(), {"reason": "faulty", "quantity": 3})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ReturnRequest.objects.exists())

    def test_unshipped_line_explains_why_and_shows_no_form(self):
        self.client.force_login(self.buyer)
        response = self.client.get(self.form_url(self.bob_item))
        self.assertContains(response, "has not been sent yet")
        self.assertNotContains(response, 'name="reason"')
        self.client.post(self.form_url(self.bob_item), {"reason": "faulty", "quantity": 1})
        self.assertFalse(ReturnRequest.objects.exists())

    def test_other_buyers_and_anonymous_users_cannot_reach_the_form(self):
        self.client.force_login(make_buyer("stranger@example.test"))
        self.assertEqual(self.client.get(self.form_url()).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.form_url()).status_code, 302)

    # -- seller --------------------------------------------------------------

    def test_seller_sees_only_their_own_returns(self):
        mine = self.make_return()
        theirs = self.make_return(order_item=self.bob_item, maker=self.bob)
        self.client.force_login(self.alice_user)
        response = self.client.get(reverse("seller_returns"))
        self.assertContains(response, reverse("seller_return_detail", args=[mine.uuid]))
        self.assertNotContains(response, reverse("seller_return_detail", args=[theirs.uuid]))
        self.assertEqual(self.client.get(reverse("seller_return_detail", args=[theirs.uuid])).status_code, 404)

    def test_status_filter(self):
        self.make_return()
        done = self.make_return(status=ReturnStatus.REFUNDED, refund_amount=Decimal("30.00"))
        self.client.force_login(self.alice_user)
        open_page = self.client.get(reverse("seller_returns"))
        self.assertNotContains(open_page, reverse("seller_return_detail", args=[done.uuid]))
        refunded = self.client.get(reverse("seller_returns") + "?status=refunded")
        self.assertContains(refunded, reverse("seller_return_detail", args=[done.uuid]))

    def test_buyers_cannot_open_seller_returns(self):
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get(reverse("seller_returns")).status_code, 403)

    def test_seller_refunds_a_return(self):
        rr = self.make_return()
        self.client.force_login(self.alice_user)
        url = reverse("seller_return_detail", args=[rr.uuid])
        response = self.client.post(url, {"action": "refund", "refund_amount": "25.00",
                                          "seller_note": "Sorry about that"})
        self.assertRedirects(response, url)
        rr.refresh_from_db()
        self.assertEqual((rr.status, rr.refund_amount), (ReturnStatus.REFUNDED, Decimal("25.00")))
        self.assertNotContains(self.client.get(url), 'name="action"')

    def test_reject_without_note_shows_error(self):
        rr = self.make_return()
        self.client.force_login(self.alice_user)
        response = self.client.post(reverse("seller_return_detail", args=[rr.uuid]), {"action": "reject"})
        self.assertContains(response, "Tell the buyer why the return was rejected.")
        rr.refresh_from_db()
        self.assertEqual(rr.status, ReturnStatus.REQUESTED)

    def test_dashboard_order_list_and_order_detail_show_open_returns(self):
        rr = self.make_return()
        self.client.force_login(self.alice_user)
        dashboard = self.client.get(reverse("seller_dashboard"))
        self.assertEqual(dashboard.context["open_return_count"], 1)
        self.assertContains(self.client.get(reverse("seller_order_list")), "1 open return")
        detail = self.client.get(reverse("seller_order_detail", args=[self.order.order_number]))
        self.assertContains(detail, reverse("seller_return_detail", args=[rr.uuid]))
