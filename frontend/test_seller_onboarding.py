"""C3: the public seller application flow (landing page, application, status).

Approval itself is C2's service; these tests use it only to reach the
approved state, and check that nothing in the public flow grants access.
"""
import re
from unittest import mock

from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import SellerApplication, User
from accounts.seller_onboarding import approve_application, reject_application
from products.models import Maker

PASSWORD = "Applicant-pass-2026!"
APPLY = "/account/seller-application/"
STATIC_OVERRIDE = {
    **settings.STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
VALID = {"shop_name": "  Kiln & Co  ", "discipline": "Ceramics", "location": "Jingdezhen",
         "description": "Small-batch stoneware."}


class OnboardingFixtures:
    def make_users(self):
        self.buyer = User.objects.create_user(email="buyer@example.test", password=PASSWORD)
        self.admin = User.objects.create_user(email="admin@example.test", password=PASSWORD, is_admin=True)

    def application_of(self, user):
        return SellerApplication.objects.filter(user=user).first()


@override_settings(STORAGES=STATIC_OVERRIDE)
class PublicEntryTests(OnboardingFixtures, TestCase):
    def setUp(self):
        self.make_users()

    def test_anonymous_visitor_can_find_and_open_the_landing_page(self):
        home = self.client.get(reverse("home"))
        self.assertContains(home, 'href="/sell/"')  # footer entry point
        landing = self.client.get(reverse("sell"))
        self.assertEqual(landing.status_code, 200)
        self.assertContains(landing, f'href="/account/register/?next={APPLY}"')
        self.assertContains(landing, f'href="/account/login/?next={APPLY}"')

    def test_application_page_requires_sign_in(self):
        response = self.client.get(APPLY)
        self.assertRedirects(response, f"/account/login/?next={APPLY}", fetch_redirect_response=False)

    def test_registration_returns_to_the_application(self):
        response = self.client.post(f"/account/register/?next={APPLY}", {
            "first_name": "New", "last_name": "Maker", "email": "new.maker@example.test",
            "password": PASSWORD,
        })
        self.assertRedirects(response, APPLY, fetch_redirect_response=False)
        user = User.objects.get(email="new.maker@example.test")
        self.assertFalse(user.is_seller)  # registering grants nothing
        self.assertEqual(self.client.get(APPLY).status_code, 200)

    def test_registration_keeps_its_normal_destination_otherwise(self):
        cases = (("no next", ""), ("external", "?next=https://evil.example/"),
                 ("protocol-relative", "?next=//evil.example/"), ("other local page", "?next=/account/orders/"))
        for i, (label, query) in enumerate(cases):
            with self.subTest(case=label):
                client = Client()
                response = client.post(f"/account/register/{query}", {
                    "first_name": "Case", "last_name": str(i), "email": f"case{i}@example.test",
                    "password": PASSWORD,
                })
                self.assertRedirects(response, reverse("account_overview"), fetch_redirect_response=False)

    def test_registration_still_merges_the_guest_bag(self):
        with mock.patch("frontend.views.merge_session_cart") as merge:
            self.client.post(f"/account/register/?next={APPLY}", {
                "first_name": "Bag", "last_name": "Keeper", "email": "bag@example.test", "password": PASSWORD,
            })
        merge.assert_called_once()

    def test_sign_in_returns_to_the_application(self):
        response = self.client.post(f"/account/login/?next={APPLY}",
                                    {"email": "buyer@example.test", "password": PASSWORD})
        self.assertRedirects(response, APPLY, fetch_redirect_response=False)


@override_settings(STORAGES=STATIC_OVERRIDE)
class ApplicationTests(OnboardingFixtures, TestCase):
    def setUp(self):
        self.make_users()
        self.client.force_login(self.buyer)

    def test_existing_buyer_applies_and_stays_a_buyer(self):
        makers_before = Maker.objects.count()
        self.assertContains(self.client.get(APPLY), 'name="shop_name"')
        response = self.client.post(APPLY, VALID)
        self.assertRedirects(response, APPLY, fetch_redirect_response=False)

        application = self.application_of(self.buyer)
        self.assertEqual((application.status, application.shop_name, application.discipline,
                          application.location, application.description),
                         ("pending", "Kiln & Co", "Ceramics", "Jingdezhen", "Small-batch stoneware."))
        self.buyer.refresh_from_db()
        self.assertFalse(self.buyer.is_seller)
        self.assertEqual(Maker.objects.count(), makers_before)

        page = self.client.get(APPLY)
        self.assertContains(page, 'data-application-state="pending"')
        self.assertContains(page, "Thank you. Your application has been sent for review.")
        self.assertNotContains(page, 'name="shop_name"')  # no second form

    def test_applicant_cannot_reach_seller_pages_before_approval(self):
        self.client.post(APPLY, VALID)
        self.assertEqual(self.client.get(reverse("seller_product_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("seller_product_create")).status_code, 403)

    def test_duplicate_submission_keeps_the_first_application(self):
        self.client.post(APPLY, VALID)
        response = self.client.post(APPLY, {**VALID, "shop_name": "Second Shop"})
        self.assertRedirects(response, APPLY, fetch_redirect_response=False)
        self.assertEqual(SellerApplication.objects.filter(user=self.buyer).count(), 1)
        self.assertEqual(self.application_of(self.buyer).shop_name, "Kiln & Co")
        self.assertContains(self.client.get(APPLY), "You have already applied.")

    def test_required_fields_and_lengths_are_validated(self):
        for field, value in (("shop_name", ""), ("discipline", "   "), ("location", ""),
                             ("shop_name", "x" * 161), ("description", "x" * 2001)):
            with self.subTest(field=field, length=len(value)):
                response = self.client.post(APPLY, {**VALID, field: value})
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
                self.assertContains(response, 'class="field-error"')
                self.assertFalse(SellerApplication.objects.exists())
        self.client.post(APPLY, {**VALID, "description": ""})  # description is optional
        self.assertEqual(self.application_of(self.buyer).description, "")

    def test_privileged_fields_cannot_be_injected(self):
        other = User.objects.create_user(email="other@example.test", password=PASSWORD)
        maker = Maker.objects.create(slug="someone-elses", name="Someone Else's",
                                     discipline="Wood", location="Hangzhou")
        self.client.post(APPLY, {**VALID, "status": "approved", "maker": maker.pk,
                                 "reviewed_by": self.admin.pk, "reviewed_at": "2026-01-01T00:00:00Z",
                                 "review_note": "approved by myself", "user": other.pk,
                                 "is_seller": "on", "is_admin": "on"})
        application = self.application_of(self.buyer)
        self.assertEqual((application.status, application.maker_id, application.reviewed_by_id,
                          application.reviewed_at, application.review_note),
                         ("pending", None, None, None, ""))
        self.assertFalse(SellerApplication.objects.filter(user=other).exists())
        self.buyer.refresh_from_db()
        self.assertFalse(self.buyer.is_seller or self.buyer.is_admin)
        self.assertIsNone(maker.owner)

    def test_applicants_see_only_their_own_application(self):
        self.client.post(APPLY, VALID)
        other = User.objects.create_user(email="neighbour@example.test", password=PASSWORD)
        neighbour = Client()
        neighbour.force_login(other)
        page = neighbour.get(APPLY)
        self.assertContains(page, 'name="shop_name"')  # their own, empty form
        self.assertNotContains(page, "Kiln &amp; Co")

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.buyer)
        self.assertEqual(client.post(APPLY, VALID).status_code, 403)
        self.assertFalse(SellerApplication.objects.exists())
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', client.get(APPLY).content.decode()).group(1)
        self.assertEqual(client.post(APPLY, {**VALID, "csrfmiddlewaretoken": token}).status_code, 302)
        self.assertTrue(SellerApplication.objects.filter(user=self.buyer).exists())


@override_settings(STORAGES=STATIC_OVERRIDE)
class ApplicationStatusTests(OnboardingFixtures, TestCase):
    def setUp(self):
        self.make_users()
        self.client.force_login(self.buyer)
        self.client.post(APPLY, VALID)
        self.application = self.application_of(self.buyer)

    def test_rejected_application_shows_the_reason_and_no_form(self):
        reject_application(self.application.pk, self.admin, "Please add photos of your work.")
        page = self.client.get(APPLY)
        self.assertContains(page, 'data-application-state="rejected"')
        self.assertContains(page, "Please add photos of your work.")
        self.assertNotContains(page, 'name="shop_name"')
        self.client.post(APPLY, VALID)  # cannot resubmit in v1
        self.assertEqual(SellerApplication.objects.filter(user=self.buyer).count(), 1)

    def test_approved_seller_goes_to_product_management(self):
        approve_application(self.application.pk, self.admin)
        response = self.client.get(APPLY)
        self.assertRedirects(response, reverse("seller_product_list"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("seller_product_list")).status_code, 200)
        self.assertContains(self.client.get(reverse("sell")), 'href="/seller/products/"')

    def test_inconsistent_accounts_get_a_notice_and_nothing_changes(self):
        cases = {
            "role without shop": lambda: User.objects.filter(pk=self.buyer.pk).update(is_seller=True),
            "shop without role": lambda: Maker.objects.create(owner=self.buyer, slug="stray", name="Stray",
                                                              discipline="Wood", location="Hangzhou"),
        }
        for label, corrupt in cases.items():
            with self.subTest(case=label):
                corrupt()
                page = self.client.get(APPLY)
                self.assertContains(page, 'data-application-state="inconsistent"')
                self.assertNotContains(page, 'name="shop_name"')
                self.client.post(APPLY, VALID)
                self.assertEqual(self.application_of(self.buyer).status, "pending")
                User.objects.filter(pk=self.buyer.pk).update(is_seller=False)
                Maker.objects.filter(owner=self.buyer).delete()

    def test_approved_application_whose_role_was_removed_is_not_repaired(self):
        approve_application(self.application.pk, self.admin)
        User.objects.filter(pk=self.buyer.pk).update(is_seller=False)
        page = self.client.get(APPLY)
        self.assertContains(page, 'data-application-state="inconsistent"')
        self.assertFalse(User.objects.get(pk=self.buyer.pk).is_seller)


@override_settings(STORAGES=STATIC_OVERRIDE, ROOT_URLCONF="config.marketplace_urls")
class MarketplaceUrlConfTests(OnboardingFixtures, TestCase):
    """The production storefront URLConf filters out admin/ and seller/ routes;
    the onboarding routes must still be there, and approved sellers must still
    reach the product editor it keeps."""

    def setUp(self):
        self.make_users()

    def test_routes_exist_and_admin_stays_hidden(self):
        self.assertEqual(reverse("sell"), "/sell/")
        self.assertEqual(reverse("seller_application"), APPLY)
        self.assertEqual(self.client.get("/sell/").status_code, 200)
        self.assertEqual(self.client.get("/admin/").status_code, 404)

    def test_full_applicant_journey(self):
        response = self.client.post(f"/account/register/?next={APPLY}", {
            "first_name": "Market", "last_name": "Maker", "email": "market@example.test", "password": PASSWORD,
        })
        self.assertRedirects(response, APPLY, fetch_redirect_response=False)
        self.client.post(APPLY, VALID)
        user = User.objects.get(email="market@example.test")
        application = self.application_of(user)
        self.assertEqual(application.status, "pending")
        self.assertFalse(user.is_seller)

        approve_application(application.pk, self.admin)
        response = self.client.get(APPLY)
        self.assertRedirects(response, "/seller/products/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/seller/products/").status_code, 200)
