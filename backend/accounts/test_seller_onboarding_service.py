"""C2: the seller application approval/rejection service.

Plain TestCase covers the rules; TransactionTestCase covers a real rollback and
two real database connections racing for the same application.
"""
import io
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock, skipUnless

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import CommandError, call_command
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase

from accounts.models import SellerApplication, User
from accounts.seller_onboarding import approve_application, reject_application
from products.models import Maker

Status = SellerApplication.Status
PASSWORD = "Onboarding-pass-2026"


class OnboardingFixtures:
    def make_people(self):
        self.applicant = User.objects.create_user(email="applicant@example.test", password=PASSWORD)
        self.admin = User.objects.create_user(email="admin@example.test", password=PASSWORD, is_admin=True)
        self.superuser = User.objects.create_superuser(email="root@example.test", password=PASSWORD)

    def make_application(self, user=None, **fields):
        values = {"shop_name": "Kiln & Co", "discipline": "Ceramics", "location": "Shanghai",
                  "description": "Small-batch stoneware."}
        values.update(fields)
        return SellerApplication.objects.create(user=user or self.applicant, **values)

    def state(self, application):
        """Everything approval could change, read fresh from the database."""
        row = SellerApplication.objects.get(pk=application.pk)
        user = User.objects.get(pk=row.user_id)
        return {
            "status": row.status, "maker": row.maker_id, "reviewed_by": row.reviewed_by_id,
            "reviewed_at": row.reviewed_at, "review_note": row.review_note,
            "is_seller": user.is_seller,
            "makers_owned": list(Maker.objects.filter(owner=user).values_list("pk", flat=True)),
        }

    def assert_unchanged(self, application, before):
        self.assertEqual(self.state(application), before)


class ApprovalTests(OnboardingFixtures, TestCase):
    def setUp(self):
        self.make_people()
        self.application = self.make_application()

    def test_approval_creates_one_matching_shop_and_grants_seller_access(self):
        self.assertFalse(self.applicant.is_seller)
        self.assertEqual(Maker.objects.filter(owner=self.applicant).count(), 0)
        makers_before = Maker.objects.count()

        result = approve_application(self.application.pk, self.admin)

        self.assertEqual(Maker.objects.count(), makers_before + 1)
        maker = Maker.objects.get(owner=self.applicant)
        self.assertEqual((maker.name, maker.discipline, maker.location, maker.short_bio, maker.is_active),
                         ("Kiln & Co", "Ceramics", "Shanghai", "Small-batch stoneware.", True))
        self.assertTrue(maker.slug.startswith("seller-") and len(maker.slug) == len("seller-") + 16)
        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_seller)
        self.assertEqual(self.applicant.maker_profile, maker)
        result.refresh_from_db()
        self.assertEqual((result.status, result.maker_id, result.reviewed_by_id),
                         (Status.APPROVED, maker.pk, self.admin.pk))
        self.assertIsNotNone(result.reviewed_at)

    def test_superuser_may_approve(self):
        approve_application(self.application.pk, self.superuser)
        self.assertEqual(self.state(self.application)["status"], Status.APPROVED)

    def test_unauthorised_reviewers_are_refused(self):
        buyer = User.objects.create_user(email="buyer@example.test", password=PASSWORD)
        staff_only = User.objects.create_user(email="staff@example.test", password=PASSWORD, is_staff=True)
        seller = User.objects.create_user(email="seller@example.test", password=PASSWORD, is_seller=True)
        inactive_admin = User.objects.create_user(email="gone@example.test", password=PASSWORD,
                                                  is_admin=True, is_active=False)
        before = self.state(self.application)
        for label, reviewer in (("anonymous", AnonymousUser()), ("none", None), ("buyer", buyer),
                                ("staff only", staff_only), ("seller", seller),
                                ("inactive admin", inactive_admin)):
            with self.subTest(reviewer=label):
                with self.assertRaises(PermissionDenied):
                    approve_application(self.application.pk, reviewer)
                with self.assertRaises(PermissionDenied):
                    reject_application(self.application.pk, reviewer, "Not yet.")
                self.assert_unchanged(self.application, before)

    def test_authority_is_read_from_the_database_not_the_callers_copy(self):
        stale_admin = User.objects.get(pk=self.admin.pk)
        User.objects.filter(pk=self.admin.pk).update(is_admin=False)  # revoked since loaded
        self.assertTrue(stale_admin.is_admin)
        with self.assertRaises(PermissionDenied):
            approve_application(self.application.pk, stale_admin)
        self.assertEqual(self.state(self.application)["status"], Status.PENDING)

    def test_reviewer_cannot_decide_their_own_application(self):
        own = self.make_application(user=self.admin, shop_name="Admin Shop")
        before = self.state(own)
        with self.assertRaises(PermissionDenied):
            approve_application(own.pk, self.admin)
        with self.assertRaises(PermissionDenied):
            reject_application(own.pk, self.admin, "Self-review.")
        self.assert_unchanged(own, before)

    def test_inactive_applicant_cannot_be_approved(self):
        User.objects.filter(pk=self.applicant.pk).update(is_active=False)
        before = self.state(self.application)
        with self.assertRaises(ValidationError) as ctx:
            approve_application(self.application.pk, self.admin)
        self.assertEqual(ctx.exception.code, "applicant_inactive")
        self.assert_unchanged(self.application, before)

    def test_applicant_already_a_seller_is_refused_not_repaired(self):
        User.objects.filter(pk=self.applicant.pk).update(is_seller=True)
        before = self.state(self.application)
        with self.assertRaises(ValidationError) as ctx:
            approve_application(self.application.pk, self.admin)
        self.assertEqual(ctx.exception.code, "inconsistent_state")
        self.assert_unchanged(self.application, before)

    def test_applicant_already_owning_a_maker_is_refused_not_attached(self):
        Maker.objects.create(owner=self.applicant, slug="legacy-shop", name="Legacy",
                             discipline="Wood", location="Hangzhou")
        before = self.state(self.application)
        with self.assertRaises(ValidationError) as ctx:
            approve_application(self.application.pk, self.admin)
        self.assertEqual(ctx.exception.code, "inconsistent_state")
        self.assert_unchanged(self.application, before)

    def test_repeat_approval_is_idempotent(self):
        approve_application(self.application.pk, self.admin)
        before = self.state(self.application)
        makers_before = Maker.objects.count()

        again = approve_application(self.application.pk, self.superuser)  # a different reviewer

        self.assert_unchanged(self.application, before)  # original reviewer and time kept
        self.assertEqual(again.reviewed_by_id, self.admin.pk)
        self.assertEqual(Maker.objects.count(), makers_before)

    def test_inconsistent_approved_record_is_reported_not_repaired(self):
        approve_application(self.application.pk, self.admin)
        cases = (
            ("seller role removed", lambda: User.objects.filter(pk=self.applicant.pk).update(is_seller=False)),
            ("shop reassigned", lambda: Maker.objects.filter(owner=self.applicant).update(owner=self.admin)),
        )
        for label, corrupt in cases:
            with self.subTest(case=label):
                with transaction.atomic():
                    corrupt()
                    before = self.state(self.application)
                    with self.assertRaises(ValidationError) as ctx:
                        approve_application(self.application.pk, self.admin)
                    self.assertEqual(ctx.exception.code, "inconsistent_state")
                    self.assert_unchanged(self.application, before)
                    transaction.set_rollback(True)  # undo this case's corruption

    def test_rejected_application_cannot_be_approved(self):
        reject_application(self.application.pk, self.admin, "Please add more detail.")
        before = self.state(self.application)
        with self.assertRaises(ValidationError) as ctx:
            approve_application(self.application.pk, self.admin)
        self.assertEqual(ctx.exception.code, "not_pending")
        self.assert_unchanged(self.application, before)

    def test_missing_application_raises_does_not_exist(self):
        with self.assertRaises(SellerApplication.DoesNotExist):
            approve_application(10**9, self.admin)


class RejectionTests(OnboardingFixtures, TestCase):
    def setUp(self):
        self.make_people()
        self.application = self.make_application()

    def test_rejection_records_the_decision_and_grants_nothing(self):
        makers_before = Maker.objects.count()
        reject_application(self.application.pk, self.admin, "  Please add photos of your work.  ")
        state = self.state(self.application)
        self.assertEqual((state["status"], state["maker"], state["reviewed_by"], state["review_note"]),
                         (Status.REJECTED, None, self.admin.pk, "Please add photos of your work."))
        self.assertIsNotNone(state["reviewed_at"])
        self.assertFalse(state["is_seller"])
        self.assertEqual(Maker.objects.count(), makers_before)

    def test_a_meaningful_reason_within_the_limit_is_required(self):
        before = self.state(self.application)
        for label, reason, code in (("empty", "", "reason_required"), ("blank", "   ", "reason_required"),
                                    ("none", None, "reason_required"),
                                    ("too long", "x" * 1001, "reason_too_long")):
            with self.subTest(reason=label):
                with self.assertRaises(ValidationError) as ctx:
                    reject_application(self.application.pk, self.admin, reason)
                self.assertEqual(ctx.exception.code, code)
                self.assert_unchanged(self.application, before)
        reject_application(self.application.pk, self.admin, "x" * 1000)  # exactly at the limit
        self.assertEqual(self.state(self.application)["status"], Status.REJECTED)

    def test_repeat_rejection_keeps_the_original_decision(self):
        reject_application(self.application.pk, self.admin, "First reason.")
        before = self.state(self.application)
        again = reject_application(self.application.pk, self.superuser, "Second reason.")
        self.assert_unchanged(self.application, before)
        self.assertEqual(again.review_note, "First reason.")

    def give_seller_state_independently(self, kind):
        """Simulate an operator granting seller access outside this flow."""
        if kind == "role only":
            User.objects.filter(pk=self.applicant.pk).update(is_seller=True)
        else:  # "maker only"
            Maker.objects.create(owner=self.applicant, slug="operator-shop", name="Operator Shop",
                                 discipline="Wood", location="Hangzhou")

    def test_pending_application_with_independent_seller_state_is_refused(self):
        for kind in ("role only", "maker only"):
            with self.subTest(kind=kind), transaction.atomic():
                self.give_seller_state_independently(kind)
                before = self.state(self.application)
                with self.assertRaises(ValidationError) as ctx:
                    reject_application(self.application.pk, self.admin, "Not a fit.")
                self.assertEqual(ctx.exception.code, "inconsistent_state")
                self.assert_unchanged(self.application, before)  # nothing revoked or recorded
                transaction.set_rollback(True)

    def test_rejected_application_with_independent_seller_state_is_refused(self):
        reject_application(self.application.pk, self.admin, "First reason.")
        for kind in ("role only", "maker only"):
            with self.subTest(kind=kind), transaction.atomic():
                self.give_seller_state_independently(kind)
                before = self.state(self.application)
                with self.assertRaises(ValidationError) as ctx:
                    reject_application(self.application.pk, self.admin, "Again.")
                self.assertEqual(ctx.exception.code, "inconsistent_state")
                self.assert_unchanged(self.application, before)
                transaction.set_rollback(True)

    def test_approved_application_cannot_be_rejected(self):
        approve_application(self.application.pk, self.admin)
        before = self.state(self.application)
        with self.assertRaises(ValidationError) as ctx:
            reject_application(self.application.pk, self.admin, "Changed my mind.")
        self.assertEqual(ctx.exception.code, "not_pending")
        self.assert_unchanged(self.application, before)


class ProvisionSellerPreservedTests(TestCase):
    """The operator command keeps its own rules; C2 does not touch it."""

    def run_command(self, email, shop="Operator Shop"):
        with tempfile.TemporaryDirectory() as tmp:
            password_file = Path(tmp) / "password"
            password_file.write_text("Operator-Provisioned-Pass-2026!", encoding="utf-8")
            call_command("provision_seller", email=email, shop=shop, password_file=password_file,
                         stdout=io.StringIO())

    def test_creates_a_new_seller_with_a_shop(self):
        self.run_command("operator.seller@example.test")
        user = User.objects.get(email="operator.seller@example.test")
        self.assertTrue(user.is_seller)
        self.assertEqual(user.maker_profile.name, "Operator Shop")
        self.assertFalse(SellerApplication.objects.filter(user=user).exists())

    def test_still_refuses_existing_accounts(self):
        existing = User.objects.create_user(email="existing@example.test", password=PASSWORD)
        with self.assertRaises(CommandError):
            self.run_command("existing@example.test")
        existing.refresh_from_db()
        self.assertFalse(existing.is_seller)
        self.assertFalse(Maker.objects.filter(owner=existing).exists())


class RollbackTests(OnboardingFixtures, TransactionTestCase):
    """Real commits and rollbacks: a failure after the shop is created undoes everything."""

    def setUp(self):
        self.make_people()
        self.application = self.make_application()

    def test_failure_late_in_approval_rolls_back_shop_role_and_status(self):
        before = self.state(self.application)
        makers_before = Maker.objects.count()
        with mock.patch.object(SellerApplication, "save", side_effect=RuntimeError("simulated failure")):
            with self.assertRaises(RuntimeError):
                approve_application(self.application.pk, self.admin)
        self.assert_unchanged(self.application, before)
        self.assertEqual(Maker.objects.count(), makers_before)
        self.assertFalse(User.objects.get(pk=self.applicant.pk).is_seller)


@skipUnless(connection.vendor == "postgresql", "lock waits are observed via pg_stat_activity")
class ConcurrencyTests(OnboardingFixtures, TransactionTestCase):
    """Request A runs in a transaction held open after it has taken its locks.
    Request B, on its own connection, is started and the test waits until
    PostgreSQL reports B's backend in a lock wait. Only then does A commit, and
    the assertions check what B did with A's committed result."""

    TIMEOUT = 10

    def setUp(self):
        self.make_people()
        self.second_admin = User.objects.create_user(email="admin2@example.test", password=PASSWORD,
                                                     is_admin=True)
        self.application = self.make_application()

    def race(self, first, second):
        outcome, box = {"first": None, "second": None}, {}
        held, release = threading.Event(), threading.Event()

        def run_first():
            try:
                with transaction.atomic():
                    outcome["first"] = first()
                    held.set()
                    release.wait(self.TIMEOUT + 5)
            except Exception as exc:  # surfaced by the assertions
                outcome["first"] = exc
                held.set()
            finally:
                connection.close()

        def run_second():
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    box["pid"] = cursor.fetchone()[0]
                outcome["second"] = second()
            except Exception as exc:
                outcome["second"] = exc
            finally:
                connection.close()

        thread_a = threading.Thread(target=run_first)
        thread_a.start()
        self.assertTrue(held.wait(self.TIMEOUT), "request A never took its locks")
        thread_b = threading.Thread(target=run_second)
        thread_b.start()
        try:
            blocked = self.wait_for_lock_wait(box)
        finally:
            release.set()
            thread_a.join(self.TIMEOUT + 10)
            thread_b.join(self.TIMEOUT + 10)
        self.assertTrue(blocked, "request B never waited on a row lock held by request A")
        self.assertNotEqual(box["pid"], connection.cursor().connection.info.backend_pid)
        return outcome

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

    def test_concurrent_approvals_create_one_shop_and_keep_the_first_decision(self):
        pk = self.application.pk
        outcome = self.race(lambda: approve_application(pk, self.admin),
                            lambda: approve_application(pk, self.second_admin))
        self.assertIsInstance(outcome["first"], SellerApplication)
        self.assertIsInstance(outcome["second"], SellerApplication)  # idempotent, not an error
        self.assertEqual(Maker.objects.filter(owner=self.applicant).count(), 1)
        state = self.state(self.application)
        self.assertEqual((state["status"], state["reviewed_by"], state["is_seller"]),
                         (Status.APPROVED, self.admin.pk, True))
        self.assertEqual(outcome["second"].reviewed_by_id, self.admin.pk)

    def test_concurrent_approve_and_reject_cannot_both_win(self):
        pk = self.application.pk
        outcome = self.race(lambda: approve_application(pk, self.admin),
                            lambda: reject_application(pk, self.second_admin, "Too late."))
        self.assertIsInstance(outcome["first"], SellerApplication)
        self.assertIsInstance(outcome["second"], ValidationError)
        self.assertEqual(outcome["second"].code, "not_pending")
        state = self.state(self.application)
        self.assertEqual((state["status"], state["review_note"], len(state["makers_owned"])),
                         (Status.APPROVED, "", 1))

    def test_concurrent_reject_and_approve_cannot_both_win(self):
        pk = self.application.pk
        outcome = self.race(lambda: reject_application(pk, self.admin, "Not a fit."),
                            lambda: approve_application(pk, self.second_admin))
        self.assertIsInstance(outcome["second"], ValidationError)
        self.assertEqual(outcome["second"].code, "not_pending")
        state = self.state(self.application)
        self.assertEqual((state["status"], state["is_seller"], state["makers_owned"]),
                         (Status.REJECTED, False, []))
