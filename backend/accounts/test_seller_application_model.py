"""C1: SellerApplication schema rules, enforced by PostgreSQL itself.

Rows are written with plain ORM create/update calls -- no forms and no
full_clean() -- so every IntegrityError below comes from the database's own
UNIQUE/CHECK constraints. Ownership consistency between `user` and
`maker.owner` is not a database rule; the approval service (C2) owns it.
"""
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from accounts.models import SellerApplication, User
from products.models import Maker

PENDING = SellerApplication.Status.PENDING
APPROVED = SellerApplication.Status.APPROVED
REJECTED = SellerApplication.Status.REJECTED


class SellerApplicationModelTests(TestCase):
    def setUp(self):
        self.applicant = User.objects.create_user(email="applicant@example.test", password="Applicant-pass-2026")
        self.reviewer = User.objects.create_user(email="reviewer@example.test", password="Reviewer-pass-2026",
                                                 is_admin=True)
        self.maker = Maker.objects.create(slug="applicant-shop", name="Applicant Shop",
                                          discipline="Ceramics", location="Singapore")

    def apply(self, user=None, **fields):
        values = {"shop_name": "Applicant Shop", "discipline": "Ceramics", "location": "Singapore"}
        values.update(fields)
        return SellerApplication.objects.create(user=user or self.applicant, **values)

    def assert_rejected_by_database(self, **fields):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.apply(**fields)
        self.assertFalse(SellerApplication.objects.exists())

    # -- defaults and privileges --------------------------------------------

    def test_new_application_is_pending_with_no_review_data(self):
        application = self.apply()
        application.refresh_from_db()
        self.assertEqual(application.status, PENDING)
        self.assertIsNone(application.reviewed_by)
        self.assertIsNone(application.reviewed_at)
        self.assertEqual(application.review_note, "")
        self.assertIsNone(application.maker)
        self.assertIsNotNone(application.uuid)

    def test_applying_grants_no_seller_privilege_and_creates_no_maker(self):
        makers_before = Maker.objects.count()
        self.apply()
        self.applicant.refresh_from_db()
        self.assertFalse(self.applicant.is_seller)
        self.assertFalse(hasattr(self.applicant, "maker_profile"))
        self.assertEqual(Maker.objects.count(), makers_before)

    # -- uniqueness ------------------------------------------------------------

    def test_one_application_per_user(self):
        self.apply()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.apply(shop_name="Second Shop")
        self.assertEqual(SellerApplication.objects.filter(user=self.applicant).count(), 1)

    def test_one_application_per_maker(self):
        self.apply(status=APPROVED, reviewed_by=self.reviewer, reviewed_at=timezone.now(), maker=self.maker)
        other = User.objects.create_user(email="other@example.test", password="Other-pass-2026")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.apply(user=other, status=APPROVED, reviewed_by=self.reviewer,
                       reviewed_at=timezone.now(), maker=self.maker)

    # -- status and review-state checks -----------------------------------------

    def test_invalid_status_is_rejected(self):
        self.assert_rejected_by_database(status="suspended")

    def test_pending_cannot_carry_review_data(self):
        now = timezone.now()
        for fields in ({"reviewed_at": now}, {"reviewed_by": self.reviewer}, {"maker": self.maker}):
            with self.subTest(fields=list(fields)):
                self.assert_rejected_by_database(status=PENDING, **fields)

    def test_approved_requires_a_review_date_and_a_maker(self):
        now = timezone.now()
        for fields in ({"reviewed_at": now}, {"maker": self.maker}, {}):
            with self.subTest(fields=list(fields)):
                self.assert_rejected_by_database(status=APPROVED, reviewed_by=self.reviewer, **fields)

    def test_rejected_requires_a_review_date_and_no_maker(self):
        now = timezone.now()
        for fields in ({}, {"reviewed_at": now, "maker": self.maker}):
            with self.subTest(fields=list(fields)):
                self.assert_rejected_by_database(status=REJECTED, reviewed_by=self.reviewer, **fields)

    def test_valid_approved_and_rejected_records_are_accepted(self):
        approved = self.apply(status=APPROVED, reviewed_by=self.reviewer,
                              reviewed_at=timezone.now(), maker=self.maker)
        other = User.objects.create_user(email="rejected@example.test", password="Rejected-pass-2026")
        rejected = self.apply(user=other, status=REJECTED, reviewed_by=self.reviewer,
                              reviewed_at=timezone.now(), review_note="Please add product photos.")
        self.assertEqual({a.pk for a in SellerApplication.objects.all()}, {approved.pk, rejected.pk})

    def test_invalid_state_is_rejected_on_update_too(self):
        application = self.apply()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SellerApplication.objects.filter(pk=application.pk).update(status=APPROVED)
        application.refresh_from_db()
        self.assertEqual(application.status, PENDING)

    def test_shop_name_discipline_and_location_are_required(self):
        for field in ("shop_name", "discipline", "location"):
            with self.subTest(field=field):
                self.assert_rejected_by_database(**{field: ""})

    # -- deletion rules --------------------------------------------------------

    def test_maker_linked_to_an_approved_application_cannot_be_deleted(self):
        self.apply(status=APPROVED, reviewed_by=self.reviewer, reviewed_at=timezone.now(), maker=self.maker)
        with self.assertRaises(ProtectedError):
            self.maker.delete()
        self.assertTrue(Maker.objects.filter(pk=self.maker.pk).exists())

    def test_deleting_the_applicant_deletes_their_application(self):
        application = self.apply()
        self.applicant.delete()
        self.assertFalse(SellerApplication.objects.filter(pk=application.pk).exists())

    def test_deleting_the_reviewer_keeps_the_decision(self):
        reviewed_at = timezone.now()
        application = self.apply(status=REJECTED, reviewed_by=self.reviewer, reviewed_at=reviewed_at,
                                 review_note="Not a fit yet.")
        self.reviewer.delete()
        application.refresh_from_db()
        self.assertIsNone(application.reviewed_by)
        self.assertEqual((application.status, application.reviewed_at, application.review_note),
                         (REJECTED, reviewed_at, "Not a fit yet."))
