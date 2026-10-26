"""C4: the administrator review pages for seller applications.

Decisions are C2's. These tests check that the pages admit only C2's
reviewers, hand every decision to the service, and change nothing themselves.
"""
import re
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import seller_onboarding
from accounts.models import SellerApplication, User
from products.models import Maker

PASSWORD = "Reviewer-pass-2026!"
LIST = "/staff/seller-applications/"
STATIC_OVERRIDE = {
    **settings.STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def detail_url(application):
    return f"{LIST}{application.uuid}/"


def approve_url(application):
    return f"{LIST}{application.uuid}/approve/"


def reject_url(application):
    return f"{LIST}{application.uuid}/reject/"


def messages_of(response):
    return [str(message) for message in response.context["messages"]]


class ReviewFixtures:
    def setUp(self):
        self.admin = User.objects.create_user(email="admin@example.test", password=PASSWORD, is_admin=True)
        self.applicant = User.objects.create_user(email="maker@example.test", password=PASSWORD)
        self.application = self.apply(self.applicant, "Kiln & Co")
        self.reviewer = self.signed_in(self.admin)

    def apply(self, user, shop_name):
        return SellerApplication.objects.create(user=user, shop_name=shop_name,
                                                discipline="Ceramics", location="Jingdezhen")

    def signed_in(self, user, **client_options):
        client = Client(**client_options)
        client.force_login(user)
        return client

    def assert_untouched(self):
        self.application.refresh_from_db()
        self.applicant.refresh_from_db()
        self.assertEqual(self.application.status, "pending")
        self.assertIsNone(self.application.reviewed_at)
        self.assertFalse(self.applicant.is_seller)
        self.assertFalse(Maker.objects.filter(owner=self.applicant).exists())


@override_settings(STORAGES=STATIC_OVERRIDE)
class AccessTests(ReviewFixtures, TestCase):
    def setUp(self):
        super().setUp()
        seller = User.objects.create_user(email="seller@example.test", password=PASSWORD, is_seller=True)
        Maker.objects.create(owner=seller, slug="seller-shop", name="Seller Shop",
                             discipline="Wood", location="Hangzhou")
        self.refused = {
            "anonymous": Client(),
            "buyer": self.signed_in(User.objects.create_user(email="buyer@example.test", password=PASSWORD)),
            "staff only": self.signed_in(User.objects.create_user(
                email="staff@example.test", password=PASSWORD, is_staff=True)),
            "seller": self.signed_in(seller),
            "inactive admin": self.signed_in(User.objects.create_user(
                email="former@example.test", password=PASSWORD, is_admin=True, is_active=False)),
        }

    def requests(self):
        return (("GET", LIST), ("GET", detail_url(self.application)),
                ("POST", approve_url(self.application)), ("POST", reject_url(self.application)))

    def test_every_route_is_a_404_for_everyone_but_administrators(self):
        for role, client in self.refused.items():
            for method, url in self.requests():
                with self.subTest(role=role, method=method, url=url):
                    if method == "GET":
                        response = client.get(url)
                    else:
                        response = client.post(url, {"reason": "No."})
                    self.assertEqual(response.status_code, 404)
                    self.assertNotContains(response, "Kiln", status_code=404)
        self.assert_untouched()

    def test_rights_are_read_from_the_database_on_every_request(self):
        self.assertEqual(self.reviewer.get(LIST).status_code, 200)
        User.objects.filter(pk=self.admin.pk).update(is_admin=False)
        for method, url in self.requests():
            with self.subTest(method=method, url=url):
                response = getattr(self.reviewer, method.lower())(url, {"reason": "No."} if method == "POST" else None)
                self.assertEqual(response.status_code, 404)
        self.assert_untouched()

    def test_administrators_and_superusers_are_admitted(self):
        superuser = User.objects.create_user(email="root@example.test", password=PASSWORD, is_superuser=True)
        for label, client in (("admin", self.reviewer), ("superuser", self.signed_in(superuser))):
            with self.subTest(role=label):
                self.assertContains(client.get(LIST), "Kiln &amp; Co")
                self.assertContains(client.get(detail_url(self.application)), "maker@example.test")

    def test_unknown_application_is_a_404(self):
        missing = SellerApplication(uuid="00000000-0000-4000-8000-000000000000")
        self.assertEqual(self.reviewer.get(detail_url(missing)).status_code, 404)
        self.assertEqual(self.reviewer.post(approve_url(missing)).status_code, 404)
        self.assertEqual(self.reviewer.post(reject_url(missing), {"reason": "No."}).status_code, 404)

    def test_get_and_head_never_decide(self):
        for method in ("get", "head"):
            for url in (approve_url(self.application), reject_url(self.application)):
                with self.subTest(method=method, url=url):
                    self.assertEqual(getattr(self.reviewer, method)(url).status_code, 405)
        self.assertEqual(self.reviewer.head(LIST).status_code, 200)
        self.assert_untouched()

    def test_csrf_is_enforced_on_decisions(self):
        client = self.signed_in(self.admin, enforce_csrf_checks=True)
        self.assertEqual(client.post(approve_url(self.application)).status_code, 403)
        self.assertEqual(client.post(reject_url(self.application), {"reason": "No."}).status_code, 403)
        self.assert_untouched()
        page = client.get(detail_url(self.application)).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
        response = client.post(approve_url(self.application), {"csrfmiddlewaretoken": token})
        self.assertRedirects(response, detail_url(self.application), fetch_redirect_response=False)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "approved")

    def test_pages_are_not_cached(self):
        self.assertIn("no-store", self.reviewer.get(LIST)["Cache-Control"])
        self.assertIn("no-store", self.reviewer.get(detail_url(self.application))["Cache-Control"])


@override_settings(STORAGES=STATIC_OVERRIDE)
class QueueTests(ReviewFixtures, TestCase):
    def age(self, application, days):
        SellerApplication.objects.filter(pk=application.pk).update(
            created_at=timezone.now() - timedelta(days=days))

    def shop_names(self, response):
        return [application.shop_name for application in response.context["page_obj"]]

    def test_pending_applications_are_listed_oldest_first_by_default(self):
        older = self.apply(User.objects.create_user(email="older@example.test"), "Older Loom")
        newest = self.apply(User.objects.create_user(email="newest@example.test"), "Newest Forge")
        self.age(older, 5)
        self.age(self.application, 2)
        self.age(newest, 0)
        decided = self.apply(User.objects.create_user(email="decided@example.test"), "Decided Studio")
        seller_onboarding.reject_application(decided.pk, self.admin, "Not a fit.")

        response = self.reviewer.get(LIST)
        self.assertEqual(response.context["status"], "pending")
        self.assertEqual(self.shop_names(response), ["Older Loom", "Kiln & Co", "Newest Forge"])
        self.assertContains(response, f'href="{detail_url(older)}"')
        self.assertContains(response, "older@example.test")
        self.assertContains(response, 'aria-current="page">Pending (3)')

    def test_status_filter_is_validated(self):
        approved = self.apply(User.objects.create_user(email="ok@example.test"), "Approved Atelier")
        seller_onboarding.approve_application(approved.pk, self.admin)
        rejected = self.apply(User.objects.create_user(email="no@example.test"), "Rejected Works")
        seller_onboarding.reject_application(rejected.pk, self.admin, "Not a fit.")
        for status, expected in (("approved", ["Approved Atelier"]), ("rejected", ["Rejected Works"]),
                                 ("pending", ["Kiln & Co"]), ("bogus", ["Kiln & Co"]), ("", ["Kiln & Co"])):
            with self.subTest(status=status):
                self.assertEqual(self.shop_names(self.reviewer.get(LIST, {"status": status})), expected)

    def test_queue_is_paginated(self):
        for i in range(30):
            self.apply(User.objects.create_user(email=f"queue{i}@example.test"), f"Queue {i}")
        first = self.reviewer.get(LIST)
        self.assertEqual(len(self.shop_names(first)), 25)
        self.assertEqual(first.context["page_obj"].paginator.num_pages, 2)
        self.assertContains(first, "?status=pending&amp;page=2")
        self.assertEqual(len(self.shop_names(self.reviewer.get(LIST, {"page": 2}))), 6)
        self.assertEqual(self.reviewer.get(LIST, {"page": 99}).context["page_obj"].number, 2)
        self.assertEqual(self.reviewer.get(LIST, {"page": "x"}).context["page_obj"].number, 1)


@override_settings(STORAGES=STATIC_OVERRIDE)
class DetailTests(ReviewFixtures, TestCase):
    def test_pending_application_shows_details_flags_and_both_controls(self):
        self.application.description = "Small-batch stoneware."
        self.application.save()
        page = self.reviewer.get(detail_url(self.application))
        for text in ("Kiln &amp; Co", "Ceramics", "Jingdezhen", "Small-batch stoneware.", "maker@example.test",
                     'data-review-status="pending"'):
            self.assertContains(page, text)
        self.assertContains(page, '<dd data-flag="active">Yes</dd>', html=False)
        self.assertContains(page, '<dd data-flag="seller">No</dd>', html=False)
        self.assertContains(page, f'action="{approve_url(self.application)}"')
        self.assertContains(page, f'action="{reject_url(self.application)}"')
        self.assertContains(page, "The applicant will see this reason on their application page.")
        self.assertNotContains(page, 'data-review-state="inconsistent"')

    def test_approved_application_shows_the_linked_shop_and_reviewer_without_controls(self):
        approved = seller_onboarding.approve_application(self.application.pk, self.admin)
        page = self.reviewer.get(detail_url(self.application))
        self.assertContains(page, 'data-review-status="approved"')
        self.assertContains(page, approved.maker.slug, count=2)  # owned and linked
        self.assertContains(page, "admin@example.test")
        self.assertContains(page, '<dd data-flag="seller">Yes</dd>', html=False)
        self.assertNotContains(page, "data-review-controls")

    def test_rejected_application_shows_the_reason_without_controls(self):
        seller_onboarding.reject_application(self.application.pk, self.admin, "Please add photos of your work.")
        page = self.reviewer.get(detail_url(self.application))
        self.assertContains(page, "Reason shown to the applicant")
        self.assertContains(page, "Please add photos of your work.")
        self.assertContains(page, "admin@example.test")
        self.assertNotContains(page, "data-review-controls")

    def test_inactive_applicant_can_be_rejected_but_not_approved(self):
        User.objects.filter(pk=self.applicant.pk).update(is_active=False)
        page = self.reviewer.get(detail_url(self.application))
        self.assertNotContains(page, f'action="{approve_url(self.application)}"')
        self.assertContains(page, f'action="{reject_url(self.application)}"')
        response = self.reviewer.post(approve_url(self.application), follow=True)
        self.assertIn("inactive", messages_of(response)[0])
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "pending")


@override_settings(STORAGES=STATIC_OVERRIDE)
class DecisionTests(ReviewFixtures, TestCase):
    def test_approval_goes_through_the_service(self):
        with mock.patch.object(seller_onboarding, "approve_application",
                               wraps=seller_onboarding.approve_application) as service:
            response = self.reviewer.post(approve_url(self.application), follow=True)
        service.assert_called_once()
        application_id, reviewer = service.call_args.args
        self.assertEqual((application_id, reviewer.pk), (self.application.pk, self.admin.pk))
        self.assertRedirects(response, detail_url(self.application))
        self.assertEqual(messages_of(response), ["Approved. The applicant now has a shop and seller access."])

        self.application.refresh_from_db()
        self.applicant.refresh_from_db()
        self.assertEqual((self.application.status, self.application.reviewed_by_id), ("approved", self.admin.pk))
        self.assertTrue(self.applicant.is_seller)
        self.assertEqual(self.application.maker.owner_id, self.applicant.pk)

    def test_rejection_goes_through_the_service(self):
        with mock.patch.object(seller_onboarding, "reject_application",
                               wraps=seller_onboarding.reject_application) as service:
            response = self.reviewer.post(reject_url(self.application),
                                          {"reason": "  Please add photos of your work.  "}, follow=True)
        service.assert_called_once()
        self.assertEqual(service.call_args.args[0], self.application.pk)
        self.assertEqual(service.call_args.args[1].pk, self.admin.pk)
        self.assertEqual(messages_of(response), ["Rejected. The applicant can now see your reason."])

        self.application.refresh_from_db()
        self.applicant.refresh_from_db()
        self.assertEqual((self.application.status, self.application.review_note),
                         ("rejected", "Please add photos of your work."))
        self.assertIsNone(self.application.maker)
        self.assertFalse(self.applicant.is_seller)
        applicant_page = self.signed_in(self.applicant).get(reverse("seller_application"))
        self.assertContains(applicant_page, "Please add photos of your work.")

    def test_view_changes_nothing_when_the_service_refuses(self):
        refusal = ValidationError("conflict", code="inconsistent_state")
        with mock.patch.object(seller_onboarding, "approve_application", side_effect=refusal):
            response = self.reviewer.post(approve_url(self.application), follow=True)
        self.assertIn("reconcile the account by hand", messages_of(response)[0])
        self.assert_untouched()

    def test_rejection_reason_is_required_and_bounded(self):
        for label, reason in (("empty", ""), ("blank", "   "), ("too long", "x" * 1001)):
            with self.subTest(case=label), mock.patch.object(seller_onboarding, "reject_application") as service:
                response = self.reviewer.post(reject_url(self.application), {"reason": reason})
                self.assertEqual(response.status_code, 200)
                self.assertIn("reason", response.context["rejection_form"].errors)
                self.assertContains(response, 'class="field-error"')
                service.assert_not_called()
        self.assert_untouched()
        self.reviewer.post(reject_url(self.application), {"reason": "x" * 1000})
        self.application.refresh_from_db()
        self.assertEqual(len(self.application.review_note), 1000)

    def test_repeated_approval_is_idempotent(self):
        self.reviewer.post(approve_url(self.application), follow=True)  # consume its message
        first = SellerApplication.objects.get(pk=self.application.pk)
        response = self.reviewer.post(approve_url(self.application), follow=True)
        self.assertEqual(messages_of(response), ["This application was already approved. Nothing was changed."])
        again = SellerApplication.objects.get(pk=self.application.pk)
        self.assertEqual((again.maker_id, again.reviewed_at), (first.maker_id, first.reviewed_at))
        self.assertEqual(Maker.objects.filter(owner=self.applicant).count(), 1)

    def test_repeated_rejection_keeps_the_original_reason(self):
        self.reviewer.post(reject_url(self.application), {"reason": "First reason."}, follow=True)
        response = self.reviewer.post(reject_url(self.application), {"reason": "Second reason."}, follow=True)
        self.assertIn("already rejected", messages_of(response)[0])
        self.application.refresh_from_db()
        self.assertEqual(self.application.review_note, "First reason.")

    def test_a_decision_is_never_overwritten(self):
        self.reviewer.post(reject_url(self.application), {"reason": "Not a fit."}, follow=True)
        response = self.reviewer.post(approve_url(self.application), follow=True)
        self.assertIn("already been decided", messages_of(response)[0])
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "rejected")

        other = self.apply(User.objects.create_user(email="second@example.test"), "Second Studio")
        self.reviewer.post(approve_url(other), follow=True)
        response = self.reviewer.post(reject_url(other), {"reason": "Changed my mind."}, follow=True)
        self.assertIn("already been decided", messages_of(response)[0])
        other.refresh_from_db()
        self.assertEqual(other.status, "approved")
        self.assertTrue(User.objects.get(email="second@example.test").is_seller)
        self.assertTrue(Maker.objects.filter(pk=other.maker_id, is_active=True).exists())

    def test_administrators_cannot_review_their_own_application(self):
        own = self.apply(self.admin, "Admin's Workshop")
        page = self.reviewer.get(detail_url(own))
        self.assertContains(page, 'data-review-state="own"')
        self.assertNotContains(page, "data-review-controls")
        for url, data in ((approve_url(own), {}), (reject_url(own), {"reason": "Mine."})):
            with self.subTest(url=url):
                response = self.reviewer.post(url, data, follow=True)
                self.assertRedirects(response, detail_url(own))
                self.assertEqual(messages_of(response), ["You can't review your own application."])
        own.refresh_from_db()
        self.assertEqual(own.status, "pending")
        self.assertFalse(User.objects.get(pk=self.admin.pk).is_seller)

    def test_rights_removed_during_the_request_are_a_404(self):
        with mock.patch.object(seller_onboarding, "approve_application", side_effect=PermissionDenied):
            self.assertEqual(self.reviewer.post(approve_url(self.application)).status_code, 404)
        self.assert_untouched()


@override_settings(STORAGES=STATIC_OVERRIDE)
class InconsistentAccountTests(ReviewFixtures, TestCase):
    def assert_flagged_and_refused(self, expected_problem):
        page = self.reviewer.get(detail_url(self.application))
        self.assertContains(page, 'data-review-state="inconsistent"')
        self.assertContains(page, expected_problem)
        self.assertNotContains(page, "data-review-controls")
        for url, data in ((approve_url(self.application), {}), (reject_url(self.application), {"reason": "No."})):
            response = self.reviewer.post(url, data, follow=True)
            self.assertTrue(any("reconcile the account by hand" in m or "already been decided" in m
                                for m in messages_of(response)), messages_of(response))

    def test_role_without_shop(self):
        User.objects.filter(pk=self.applicant.pk).update(is_seller=True)
        self.assert_flagged_and_refused("The applicant already has the seller role.")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "pending")
        self.assertTrue(User.objects.get(pk=self.applicant.pk).is_seller)  # not revoked
        self.assertFalse(Maker.objects.filter(owner=self.applicant).exists())  # not created

    def test_shop_without_role(self):
        stray = Maker.objects.create(owner=self.applicant, slug="stray", name="Stray",
                                     discipline="Wood", location="Hangzhou")
        self.assert_flagged_and_refused("The applicant already owns a shop.")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "pending")
        self.assertTrue(Maker.objects.filter(pk=stray.pk, owner=self.applicant).exists())  # not deleted
        self.assertFalse(User.objects.get(pk=self.applicant.pk).is_seller)  # not granted

    def test_approved_application_whose_role_was_removed_is_not_repaired(self):
        seller_onboarding.approve_application(self.application.pk, self.admin)
        User.objects.filter(pk=self.applicant.pk).update(is_seller=False)
        self.assert_flagged_and_refused("The applicant no longer has the seller role.")
        self.assertFalse(User.objects.get(pk=self.applicant.pk).is_seller)


@override_settings(STORAGES=STATIC_OVERRIDE, ROOT_URLCONF="config.marketplace_urls")
class MarketplaceUrlConfTests(ReviewFixtures, TestCase):
    def test_routes_exist_and_the_django_admin_stays_hidden(self):
        self.assertEqual(reverse("staff_seller_applications"), LIST)
        self.assertEqual(reverse("staff_seller_application_detail", args=[self.application.uuid]),
                         detail_url(self.application))
        self.assertEqual(self.client.get("/admin/").status_code, 404)
        self.assertEqual(self.client.get(LIST).status_code, 404)

    def test_review_and_approval_work(self):
        self.assertContains(self.reviewer.get(LIST), "Kiln &amp; Co")
        response = self.reviewer.post(approve_url(self.application))
        self.assertRedirects(response, detail_url(self.application), fetch_redirect_response=False)
        applicant = self.signed_in(self.applicant)
        self.assertEqual(applicant.get("/seller/products/").status_code, 200)
        self.assertEqual(applicant.get(LIST).status_code, 404)  # a seller is not a reviewer

    def test_rejection_works(self):
        self.reviewer.post(reject_url(self.application), {"reason": "Not a fit."})
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "rejected")


@override_settings(STORAGES=STATIC_OVERRIDE)
class DefaultUrlConfTests(ReviewFixtures, TestCase):
    def test_routes_resolve_alongside_the_django_admin(self):
        self.assertEqual(reverse("staff_seller_applications"), LIST)
        self.assertEqual(self.client.get("/admin/").status_code, 302)  # the default deployment keeps it
        self.assertEqual(self.reviewer.get(LIST).status_code, 200)
