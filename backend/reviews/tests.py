"""Storefront review UX and shared public API permission regressions."""

from datetime import datetime, timezone

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from frontend.review_forms import ReviewForm
from orders.models import Order
from orders.tests.factories import make_buyer, make_category, make_maker, make_order_item, make_product

from .models import Review


class ReviewFormTests(SimpleTestCase):
    def test_rejects_surrogates_without_attempting_database_encoding(self):
        for field in ("title", "body"):
            with self.subTest(field=field):
                form = ReviewForm({"rating": "4", field: "bad\ud800text"})
                self.assertFalse(form.is_valid())
                self.assertEqual(form.errors.as_data()[field][0].code, "invalid_characters")


@override_settings(
    LANGUAGE_CODE="en", TIME_ZONE="UTC", SECURE_SSL_REDIRECT=False,
    STORAGES={**settings.STORAGES,
              "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
)
class ReviewFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buyer = make_buyer()
        cls.other = make_buyer("other@example.test")
        maker = make_maker("review-maker", "Review Maker")
        category = make_category()
        cls.product = make_product(maker=maker, category=category, slug="review-piece")
        cls.other_product = make_product(maker=maker, category=category, slug="other-piece")

    def setUp(self):
        self.url = reverse("product_detail", args=[self.product.slug])
        self.api_url = reverse("review-list")
        self.data = {"rating": "4", "title": "Lovely cup", "body": "Comfortable to hold."}
        self.client.force_login(self.buyer)
        self.api = APIClient()
        self.api.force_login(self.buyer)

    def purchase(self, payment_status="paid", *, user=None, product=None, status="confirmed"):
        order = Order.objects.create(
            order_number=f"REVIEW-{Order.objects.count() + 1}", user=user or self.buyer,
            customer_email=(user or self.buyer).email, payment_status=payment_status, status=status,
        )
        return make_order_item(order=order, product=product or self.product)

    def api_submit(self, **fields):
        return self.api.post(self.api_url, {"product": self.product.slug, **self.data, **fields},
                             format="json")

    def assert_field_error(self, data, field, code):
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Location", response.headers)
        form = response.context["review_form"]
        self.assertTrue(form.is_bound)
        self.assertIn(code, [error.code for error in form.errors.as_data()[field]])
        self.assertContains(response, f'id="review-{field}-errors" role="alert"')
        self.assertContains(response, f'aria-describedby="review-{field}-errors"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertFalse(Review.objects.exists())
        return response

    def test_eligible_submission_saves_trimmed_text_and_shows_success_once(self):
        item = self.purchase()
        self.assertTrue(self.client.get(self.url).context["can_review"])
        response = self.client.post(self.url, {
            "rating": "4", "title": "  Lovely cup  ", "body": "  First line\nSecond line  ",
        }, follow=True)
        self.assertRedirects(response, self.url)
        review = Review.objects.get()
        self.assertEqual((review.rating, review.title, review.body),
                         (4, "Lovely cup", "First line\nSecond line"))
        self.assertEqual((review.user_id, review.product_id, review.order_item_id),
                         (self.buyer.pk, self.product.pk, item.pk))
        self.assertTrue(review.is_published)
        self.assertContains(response, 'role="status">Thank you for reviewing this piece.', count=1)
        self.assertContains(response, "Lovely cup")
        self.assertNotContains(response, 'id="review-rating"')
        self.assertNotContains(self.client.get(self.url), "Thank you for reviewing this piece.")
        self.assertEqual(Review.objects.count(), 1)

    def test_logged_out_prompt_and_post_login_return(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertContains(response, "to review a product you have purchased")
        self.assertContains(response, reverse("login") + "?next=" + self.url)
        self.assertNotContains(response, 'id="review-rating"')
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login") + "?next=" + self.url)
        response = self.client.post(response.url, {
            "email": self.buyer.email, "password": "test-pass-12345",
        })
        self.assertEqual(response.url, self.url)
        self.assertFalse(Review.objects.exists())

    def test_non_buyer_sees_explanation_and_direct_post_is_rejected(self):
        response = self.client.get(self.url)
        self.assertContains(response, "after purchasing it and completing payment")
        self.assertNotContains(response, 'id="review-rating"')
        response = self.client.post(self.url, self.data, follow=True)
        self.assertRedirects(response, self.url)
        self.assertContains(response, 'role="alert">Only verified buyers can review this product.')
        self.assertFalse(Review.objects.exists())

    def test_every_non_paid_status_is_ineligible(self):
        item = self.purchase("unpaid")
        for payment_status in ("unpaid", "pending", "failed", "refunded"):
            with self.subTest(payment_status=payment_status):
                item.order.payment_status = payment_status
                item.order.save()
                self.assertFalse(self.client.get(self.url).context["can_review"])
                response = self.client.post(self.url, self.data, follow=True)
                self.assertContains(response, "Only verified buyers can review this product.")
                self.assertEqual(self.api_submit().status_code, 403)
                self.assertFalse(Review.objects.exists())

    def test_other_buyers_and_other_products_do_not_grant_eligibility(self):
        self.purchase(user=self.other)
        self.purchase(product=self.other_product)
        self.assertFalse(self.client.get(self.url).context["can_review"])
        self.client.post(self.url, self.data)
        self.assertEqual(self.api_submit().status_code, 403)
        self.assertFalse(Review.objects.exists())

    def test_existing_review_hides_form_and_duplicate_is_rejected(self):
        self.purchase()
        self.client.post(self.url, self.data)
        response = self.client.get(self.url)
        self.assertContains(response, "You have already submitted a review for this product.")
        self.assertNotContains(response, 'id="review-rating"')
        response = self.client.post(self.url, self.data, follow=True)
        self.assertContains(response, "You have already reviewed this product.", count=1)
        self.assertEqual(self.api_submit().status_code, 400)
        self.assertEqual(Review.objects.count(), 1)

    def test_unpublished_review_hides_form_without_exposing_review_content(self):
        self.purchase()
        Review.objects.create(user=self.buyer, product=self.product, rating=4,
                              title="Hidden title", body="Hidden body", is_published=False)
        response = self.client.get(self.url)
        self.assertFalse(response.context["can_review"])
        self.assertContains(response, "You have already submitted a review for this product.")
        for text in ('id="review-rating"', "Hidden title", "Hidden body"):
            self.assertNotContains(response, text)
        response = self.client.post(self.url, self.data, follow=True)
        self.assertContains(response, "You have already reviewed this product.")
        self.assertFalse(response.context["can_review"])
        self.assertEqual(self.api_submit().status_code, 400)
        self.assertEqual(Review.objects.count(), 1)

    def test_missing_rating_is_required(self):
        self.purchase()
        for data in ({"title": "Keep title", "body": "Keep body"},
                     {"rating": "", "title": "Keep title", "body": "Keep body"}):
            self.assert_field_error(data, "rating", "required")

    def test_invalid_rating_values_are_rejected_and_preserved(self):
        self.purchase()
        for rating in ("0", "6", "-1", "3.5", "3.0", "abc"):
            with self.subTest(rating=rating):
                response = self.assert_field_error({**self.data, "rating": rating},
                                                   "rating", "invalid_choice")
                self.assertContains(response, f'<option value="{rating}" selected>')
                self.assertContains(response, 'value="Lovely cup"')
                self.assertContains(response, "Comfortable to hold.")

    def test_all_five_integer_ratings_are_accepted(self):
        self.purchase()
        for rating in range(1, 6):
            with self.subTest(rating=rating):
                self.client.post(self.url, {**self.data, "rating": str(rating)})
                self.assertEqual(Review.objects.get().rating, rating)
                Review.objects.all().delete()

    def test_overlong_title_is_rejected_without_truncation_and_values_survive(self):
        self.purchase()
        title = "T" * 161
        response = self.assert_field_error({**self.data, "title": title}, "title", "max_length")
        self.assertContains(response, f'value="{title}"')
        self.assertContains(response, '<option value="4" selected>')
        self.assertContains(response, self.data["body"])
        self.assertEqual(response.context["review_form"]["title"].value(), title)
        response = self.client.post(self.url, {**self.data, "title": "T" * 160})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(Review.objects.get().title), 160)

    def test_control_characters_are_field_errors_instead_of_server_errors(self):
        self.purchase()
        for field in ("title", "body"):
            for control in ("\x00", "\x01", "\x1f", "\x7f", "\x85"):
                with self.subTest(field=field, control=repr(control)):
                    value = control + "Keep this text" + control
                    response = self.assert_field_error({**self.data, field: value},
                                                       field, "invalid_characters")
                    self.assertEqual(response.context["review_form"][field].value(), value)
                    self.assertContains(response, '<option value="4" selected>')

    def test_body_accepts_line_breaks_and_tabs_but_title_stays_single_line(self):
        self.purchase()
        self.assert_field_error({**self.data, "title": "Two\nlines"}, "title", "invalid_characters")
        self.client.post(self.url, {**self.data, "body": " First\r\n\tSecond\n\nThird "})
        self.assertEqual(Review.objects.get().body, "First\r\n\tSecond\n\nThird")

    def test_title_and_body_can_be_omitted_empty_or_whitespace(self):
        self.purchase()
        for fields in ({}, {"title": "", "body": ""}, {"title": "   ", "body": " \r\n\t "}):
            with self.subTest(fields=fields):
                self.assertEqual(self.client.post(self.url, {"rating": "5", **fields}).status_code, 302)
                self.assertEqual((Review.objects.get().title, Review.objects.get().body), ("", ""))
                Review.objects.all().delete()

    def test_invalid_bound_values_are_html_escaped(self):
        self.purchase()
        payload = '<script>alert("review")</script>'
        response = self.assert_field_error({"rating": payload, "title": payload, "body": payload},
                                           "rating", "invalid_choice")
        self.assertNotContains(response, payload)
        self.assertContains(response, "&lt;script&gt;")
        self.assertEqual(response.context["review_form"]["body"].value(), payload)

    def test_public_author_label_is_consistent_and_never_falls_back_to_email(self):
        self.purchase()
        self.client.post(self.url, self.data)
        self.client.logout()
        self.api.logout()
        for first, last, label in (("Buyer", "Test", "Buyer Test"), ("", "", "Customer"),
                                   ("  ", " ", "Customer"),
                                   (self.buyer.email, "", "Customer")):
            with self.subTest(first=first, last=last):
                self.buyer.first_name, self.buyer.last_name = first, last
                self.buyer.save()
                response = self.client.get(self.url)
                self.assertContains(response, label)
                self.assertNotContains(response, self.buyer.email)
                response = self.api.get(self.api_url, {"product": self.product.slug})
                self.assertEqual(response.data["items"][0]["author"], label)
                self.assertNotIn(self.buyer.email, str(response.data))
                detail = self.api.get(reverse("review-detail", args=[Review.objects.get().uuid]))
                self.assertEqual(detail.data["author"], label)
                self.assertNotIn(self.buyer.email, str(detail.data))

    def test_review_display_has_date_rating_badge_and_safe_line_breaks(self):
        self.purchase()
        self.client.post(self.url, {**self.data, "body": "First\nSecond\n\n<script>bad</script>"})
        Review.objects.update(created_at=datetime(2026, 9, 8, 12, 30, tzinfo=timezone.utc))
        response = self.client.get(self.url)
        self.assertContains(response, '<time datetime="2026-09-08T12:30:00+00:00">8 Sep 2026</time>')
        self.assertContains(response, "4 / 5")
        self.assertContains(response, "Verified purchase")
        self.assertContains(response, "Lovely cup")
        self.assertContains(response, "First<br>Second<br><br>&lt;script&gt;bad&lt;/script&gt;")
        self.assertNotContains(response, "<script>bad</script>")

    def test_review_display_excludes_other_products_and_unpublished_reviews(self):
        Review.objects.create(user=self.buyer, product=self.product, rating=4, title="First public")
        Review.objects.create(user=self.other, product=self.product, rating=5, title="Latest public")
        Review.objects.create(user=self.buyer, product=self.other_product, rating=2, title="Other product")
        response = self.client.get(self.url)
        self.assertEqual(list(response.context["reviews"].values_list("title", flat=True)),
                         ["Latest public", "First public"])
        self.assertNotContains(response, "Other product")
        Review.objects.filter(user=self.other).update(is_published=False)
        self.assertNotContains(self.client.get(self.url), "Latest public")
        self.assertEqual(self.api.get(self.api_url, {"product": self.product.slug}).data["total"], 1)

    def test_forged_storefront_fields_cannot_set_author_order_product_or_publication(self):
        item = self.purchase()
        other_item = self.purchase(user=self.other)
        self.client.post(self.url, {**self.data, "user": self.other.pk, "author": "Forged",
                                  "order_item": other_item.pk, "is_published": "false",
                                  "product": self.other_product.slug, "is_verified_purchase": "false"})
        review = Review.objects.get()
        self.assertEqual((review.user_id, review.product_id, review.order_item_id, review.is_published),
                         (self.buyer.pk, self.product.pk, item.pk, True))

    def test_forged_api_fields_are_ignored(self):
        item = self.purchase()
        other_item = self.purchase(user=self.other)
        response = self.api_submit(user=self.other.pk, author="Forged", order_item=other_item.pk,
                                   is_published=False, is_verified_purchase=False)
        self.assertEqual(response.status_code, 201)
        review = Review.objects.get()
        self.assertEqual((review.user_id, review.order_item_id, review.is_published),
                         (self.buyer.pk, item.pk, True))
        self.assertEqual(response.data["author"], "Buyer Test")

    def test_api_anonymous_and_non_buyer_cannot_create(self):
        self.assertEqual(self.api_submit().status_code, 403)
        self.api.logout()
        self.assertEqual(self.api_submit().status_code, 401)
        self.assertFalse(Review.objects.exists())

    def test_api_validation_still_rejects_bad_ratings_and_overlong_title(self):
        self.purchase()
        for fields, field in (({"rating": None}, "rating"), ({"rating": 0}, "rating"),
                              ({"rating": 6}, "rating"), ({"rating": "bad"}, "rating"),
                              ({"title": "T" * 161}, "title"), ({"body": "bad\x00text"}, "body")):
            with self.subTest(fields=fields):
                response = self.api_submit(**fields)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data["errors"])
                self.assertFalse(Review.objects.exists())

    def test_api_ownership_and_product_move_protections_remain(self):
        self.purchase()
        self.api_submit()
        url = reverse("review-detail", args=[Review.objects.get().uuid])
        self.api.force_login(self.other)
        self.assertEqual(self.api.patch(url, {"body": "Forged"}, format="json").status_code, 404)
        self.assertEqual(self.api.delete(url).status_code, 404)
        self.api.force_login(self.buyer)
        self.assertEqual(self.api.patch(url, {"product": self.other_product.slug}, format="json").status_code, 400)

    def test_csrf_still_required_on_both_session_endpoints(self):
        self.purchase()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.buyer)
        self.assertEqual(strict.post(self.url, self.data).status_code, 403)
        self.assertEqual(strict.post(self.api_url, {"product": self.product.slug, **self.data}).status_code, 403)
        self.assertFalse(Review.objects.exists())
        strict.get(self.url)
        response = strict.post(self.url, self.data, HTTP_X_CSRFTOKEN=strict.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Review.objects.count(), 1)

    def test_paid_cancelled_order_and_later_refund_policy_is_unchanged(self):
        item = self.purchase(status="cancelled")
        self.assertTrue(self.client.get(self.url).context["can_review"])
        self.client.post(self.url, self.data)
        item.order.payment_status = "refunded"
        item.order.save()
        response = self.client.get(self.url)
        self.assertContains(response, "Lovely cup")
        self.assertContains(response, "Verified purchase")
        self.assertFalse(response.context["can_review"])

    def test_mock_payment_completion_enables_review(self):
        from payments.models import Payment
        from payments.services import MockPaymentProvider

        item = self.purchase("unpaid", status="pending")
        payment = Payment.objects.create(order=item.order, provider_session_id="review-test-session")
        self.assertFalse(self.client.get(self.url).context["can_review"])
        MockPaymentProvider().confirm(payment)
        self.assertTrue(self.client.get(self.url).context["can_review"])
        self.assertEqual(self.client.post(self.url, self.data).status_code, 302)
        self.assertEqual(Review.objects.count(), 1)
