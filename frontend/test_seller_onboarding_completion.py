"""C5: seller onboarding completion -- the sign-in/registration switch, Chinese
translations, the stricter applicant seller-state check, duplicate-submission
races and role-appropriate navigation.
"""
import threading
import time
from unittest import mock, skipUnless

from django.conf import settings
from django.db import IntegrityError, connection
from django.test import Client, TestCase, TransactionTestCase, override_settings

from accounts import seller_onboarding
from accounts.models import SellerApplication, User
from products.models import Maker

from frontend.forms_onboarding import SellerApplicationForm

PASSWORD = "Completion-pass-2026!"
APPLY = "/account/seller-application/"
STAFF = "/staff/seller-applications/"
STATIC_OVERRIDE = {
    **settings.STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
VALID = {"shop_name": "Kiln & Co", "discipline": "Ceramics", "location": "Jingdezhen", "description": ""}


def signed_in(user):
    client = Client()
    client.force_login(user)
    return client


@override_settings(STORAGES=STATIC_OVERRIDE)
class AuthSwitchTests(TestCase):
    def test_switch_links_keep_the_seller_application_destination(self):
        login = self.client.get(f"/account/login/?next={APPLY}")
        self.assertContains(login, f'href="/account/register/?next={APPLY}"')
        register = self.client.get(f"/account/register/?next={APPLY}")
        self.assertContains(register, f'href="/account/login/?next={APPLY}"')

    def test_switch_links_never_carry_any_other_destination(self):
        for label, query in (("none", ""), ("external", "?next=https://evil.example/"),
                             ("protocol-relative", "?next=//evil.example/"),
                             ("other local page", "?next=/account/orders/"),
                             ("application with extra query", f"?next={APPLY}%3Fx%3D1"),
                             ("encoded external", "?next=%2F%2Fevil.example%2F")):
            with self.subTest(case=label):
                login = self.client.get(f"/account/login/{query}")
                self.assertContains(login, 'href="/account/register/">')
                self.assertNotContains(login, 'href="/account/register/?')
                register = self.client.get(f"/account/register/{query}")
                self.assertContains(register, 'href="/account/login/">')
                self.assertNotContains(register, 'href="/account/login/?')

    def test_a_visitor_can_switch_to_registration_and_still_land_on_the_application(self):
        login = self.client.get(f"/account/login/?next={APPLY}")
        self.assertContains(login, f'href="/account/register/?next={APPLY}"')
        response = self.client.post(f"/account/register/?next={APPLY}", {
            "first_name": "Switch", "last_name": "Maker", "email": "switch@example.test", "password": PASSWORD,
        })
        self.assertRedirects(response, APPLY, fetch_redirect_response=False)

    def test_sign_in_keeps_its_existing_safe_next_handling(self):
        User.objects.create_user(email="buyer@example.test", password=PASSWORD)
        response = self.client.post("/account/login/?next=/account/orders/",
                                    {"email": "buyer@example.test", "password": PASSWORD})
        self.assertRedirects(response, "/account/orders/", fetch_redirect_response=False)
        response = Client().post("/account/login/?next=https://evil.example/",
                                 {"email": "buyer@example.test", "password": PASSWORD})
        self.assertRedirects(response, "/account/", fetch_redirect_response=False)


@override_settings(STORAGES=STATIC_OVERRIDE)
class SellerStateTests(TestCase):
    def test_approved_application_linked_to_a_different_shop_is_inconsistent_and_not_repaired(self):
        admin = User.objects.create_user(email="admin@example.test", password=PASSWORD, is_admin=True)
        applicant = User.objects.create_user(email="maker@example.test", password=PASSWORD)
        application = SellerApplication.objects.create(user=applicant, **VALID)
        approved = seller_onboarding.approve_application(application.pk, admin)
        # An operator moves the approved shop to someone else and gives the applicant another one.
        linked = approved.maker
        linked.owner = User.objects.create_user(email="other@example.test", password=PASSWORD)
        linked.save()
        other_shop = Maker.objects.create(owner=applicant, slug="other-shop", name="Other Shop",
                                          discipline="Wood", location="Hangzhou")

        client = signed_in(applicant)
        page = client.get(APPLY)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'data-application-state="inconsistent"')
        self.assertNotContains(client.get("/sell/"), 'href="/seller/products/"')

        application.refresh_from_db()
        applicant.refresh_from_db()
        self.assertEqual((application.status, application.maker_id), ("approved", linked.pk))
        self.assertTrue(applicant.is_seller)
        self.assertEqual(Maker.objects.get(pk=other_shop.pk).owner_id, applicant.pk)

    def test_consistent_seller_is_still_sent_to_product_management(self):
        admin = User.objects.create_user(email="admin@example.test", password=PASSWORD, is_admin=True)
        applicant = User.objects.create_user(email="maker@example.test", password=PASSWORD)
        application = SellerApplication.objects.create(user=applicant, **VALID)
        seller_onboarding.approve_application(application.pk, admin)
        response = signed_in(applicant).get(APPLY)
        self.assertRedirects(response, "/seller/products/", fetch_redirect_response=False)


@override_settings(STORAGES=STATIC_OVERRIDE)
class IntegrityErrorTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(email="buyer@example.test", password=PASSWORD)
        self.client.force_login(self.buyer)

    def test_a_submission_that_loses_the_race_is_told_it_already_applied(self):
        original_save = SellerApplicationForm.save

        def another_tab_wins_first(form, commit=True):
            SellerApplication.objects.create(user=self.buyer, **{**VALID, "shop_name": "First Tab"})
            return original_save(form, commit=commit)

        with mock.patch.object(SellerApplicationForm, "save", autospec=True, side_effect=another_tab_wins_first):
            response = self.client.post(APPLY, {**VALID, "shop_name": "Second Tab"})
        self.assertRedirects(response, APPLY, fetch_redirect_response=False)
        self.assertEqual(list(SellerApplication.objects.filter(user=self.buyer).values_list("shop_name", flat=True)),
                         ["First Tab"])
        self.assertContains(self.client.get(APPLY), "You have already applied.")

    def test_an_unexpected_integrity_error_is_not_reported_as_a_duplicate(self):
        original_save = SellerApplicationForm.save

        def break_a_database_check(form, commit=True):
            application = original_save(form, commit=commit)
            application.shop_name = ""  # violates seller_application_required_text
            return application

        with mock.patch.object(SellerApplicationForm, "save", autospec=True, side_effect=break_a_database_check):
            with self.assertRaises(IntegrityError):
                self.client.post(APPLY, VALID)
        self.assertFalse(SellerApplication.objects.exists())
        page = self.client.get(APPLY)
        self.assertNotContains(page, "You have already applied.")
        self.assertContains(page, 'name="shop_name"')


@skipUnless(connection.vendor == "postgresql", "lock waits are observed via pg_stat_activity")
@override_settings(STORAGES=STATIC_OVERRIDE)
class ConcurrentSubmissionTests(TransactionTestCase):
    """Two real requests on two connections. The first is held open after its
    INSERT; the second is released only once PostgreSQL reports it waiting on
    the first's uncommitted row, so both really did pass the "no application
    yet" check before either committed."""

    TIMEOUT = 10

    def wait_for_lock_wait(self, box):
        deadline = time.monotonic() + self.TIMEOUT
        while time.monotonic() < deadline:
            if box.get("pid") is not None:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [box["pid"]])
                    row = cursor.fetchone()
                if row and row[0] == "Lock":
                    return True
            time.sleep(0.02)
        return False

    def test_simultaneous_submissions_keep_one_application_and_both_redirect(self):
        buyer = User.objects.create_user(email="buyer@example.test", password=PASSWORD)
        first, second = signed_in(buyer), signed_in(buyer)
        held, release = threading.Event(), threading.Event()
        responses, box = {}, {}
        original_save = SellerApplication.save

        def save_then_hold(instance, *args, **kwargs):
            original_save(instance, *args, **kwargs)
            if threading.current_thread().name == "first":
                held.set()
                release.wait(self.TIMEOUT + 5)

        def submit(client, shop_name):
            name = threading.current_thread().name
            try:
                if name == "second":
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_backend_pid()")
                        box["pid"] = cursor.fetchone()[0]
                responses[name] = client.post(APPLY, {**VALID, "shop_name": shop_name})
            except Exception as exc:  # surfaced by the assertions
                responses[name] = exc
                held.set()
            finally:
                connection.close()

        with mock.patch.object(SellerApplication, "save", autospec=True, side_effect=save_then_hold):
            thread_a = threading.Thread(target=submit, name="first", args=(first, "First Tab"))
            thread_a.start()
            self.assertTrue(held.wait(self.TIMEOUT), "the first submission never inserted")
            thread_b = threading.Thread(target=submit, name="second", args=(second, "Second Tab"))
            thread_b.start()
            try:
                blocked = self.wait_for_lock_wait(box)
            finally:
                release.set()
                thread_a.join(self.TIMEOUT + 10)
                thread_b.join(self.TIMEOUT + 10)

        self.assertTrue(blocked, "the second submission never waited on the first's row")
        for name in ("first", "second"):
            self.assertNotIsInstance(responses[name], Exception, responses[name])
            self.assertEqual((responses[name].status_code, responses[name]["Location"]), (302, APPLY))
        self.assertEqual(list(SellerApplication.objects.filter(user=buyer).values_list("shop_name", flat=True)),
                         ["First Tab"])
        self.assertContains(first.get(APPLY), "Thank you. Your application has been sent for review.")
        self.assertContains(second.get(APPLY), "You have already applied.")


@override_settings(STORAGES=STATIC_OVERRIDE)
class NavigationTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(email="buyer@example.test", password=PASSWORD)
        self.admin = User.objects.create_user(email="admin@example.test", password=PASSWORD, is_admin=True)

    def test_buyers_see_their_application_link_and_no_review_link(self):
        client = signed_in(self.buyer)
        overview = client.get("/account/")
        self.assertContains(overview, f'<a href="{APPLY}">Seller application</a>', html=True)
        self.assertNotContains(overview, STAFF)
        self.assertContains(client.get(APPLY), f'href="{APPLY}" aria-current="page"')

    def test_sellers_keep_their_seller_links_instead(self):
        seller = User.objects.create_user(email="seller@example.test", password=PASSWORD, is_seller=True)
        Maker.objects.create(owner=seller, slug="seller-shop", name="Seller Shop",
                             discipline="Wood", location="Hangzhou")
        overview = signed_in(seller).get("/account/")
        self.assertContains(overview, "Seller dashboard")
        self.assertNotContains(overview, f'href="{APPLY}"')
        self.assertNotContains(overview, STAFF)

    def test_only_current_administrators_see_the_review_link(self):
        staff_only = User.objects.create_user(email="staff@example.test", password=PASSWORD, is_staff=True)
        superuser = User.objects.create_user(email="root@example.test", password=PASSWORD, is_superuser=True)
        self.assertNotContains(signed_in(staff_only).get("/account/"), STAFF)
        self.assertContains(signed_in(superuser).get("/account/"), f'href="{STAFF}"')
        admin = signed_in(self.admin)
        self.assertContains(admin.get("/account/"), f'href="{STAFF}"')
        User.objects.filter(pk=self.admin.pk).update(is_admin=False)
        self.assertNotContains(admin.get("/account/"), STAFF)

    def test_review_pages_link_back_through_breadcrumbs(self):
        application = SellerApplication.objects.create(user=self.buyer, **VALID)
        admin = signed_in(self.admin)
        queue = admin.get(STAFF)
        self.assertContains(queue, 'class="breadcrumbs"')
        self.assertContains(queue, 'href="/account/"')
        detail = admin.get(f"{STAFF}{application.uuid}/")
        self.assertContains(detail, f'href="{STAFF}?status=pending"')
        self.assertContains(detail, 'aria-current="page">Kiln &amp; Co</span>')

    @override_settings(ROOT_URLCONF="config.marketplace_urls")
    def test_navigation_renders_under_the_marketplace_urlconf(self):
        self.assertContains(signed_in(self.buyer).get("/account/"), f'href="{APPLY}"')
        self.assertContains(signed_in(self.admin).get("/account/"), f'href="{STAFF}"')
        self.assertEqual(self.client.get("/admin/").status_code, 404)


@override_settings(STORAGES=STATIC_OVERRIDE)
class ChineseTranslationTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(email="buyer@example.test", password=PASSWORD)
        self.admin = User.objects.create_user(email="admin@example.test", password=PASSWORD, is_admin=True)

    def zh(self, user=None):
        client = signed_in(user) if user else Client()
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = "zh-hans"
        return client

    def test_landing_page(self):
        page = self.zh().get("/sell/")
        for text in ("成为卖家", "申请流程", "创建账户以申请"):
            self.assertContains(page, text)
        for text in ("Sell with us", "How it works", "Create an account to apply"):
            self.assertNotContains(page, text)

    def test_application_form_and_status(self):
        client = self.zh(self.buyer)
        form = client.get(APPLY)
        for text in ("卖家申请", "关于您的店铺", "店铺名称", "提交申请"):
            self.assertContains(form, text)
        self.assertNotContains(form, "Submit application")
        status = client.post(APPLY, VALID, follow=True)
        self.assertContains(status, "审核中")
        self.assertContains(status, "谢谢，您的申请已提交审核。")
        self.assertContains(client.post(APPLY, VALID, follow=True), "您已提交过申请，申请状态见下方。")

    def test_administrator_review_workflow(self):
        application = SellerApplication.objects.create(user=self.buyer, **VALID)
        client = self.zh(self.admin)
        self.assertContains(client.get(STAFF), "待审核 (1)")
        detail = client.get(f"{STAFF}{application.uuid}/")
        for text in ("通过申请", "拒绝申请", "给申请人的理由", "申请人将在其申请页面看到此理由。", "最多 1000 个字符。"):
            self.assertContains(detail, text)
        self.assertNotContains(detail, "Approve application")
        empty = client.post(f"{STAFF}{application.uuid}/reject/", {"reason": " "})
        self.assertContains(empty, "请填写拒绝理由。")
        done = client.post(f"{STAFF}{application.uuid}/reject/", {"reason": "需要作品照片。"}, follow=True)
        self.assertContains(done, "已拒绝。申请人现在可以看到您填写的理由。")
        self.assertContains(self.zh(self.buyer).get(APPLY), "未通过")
