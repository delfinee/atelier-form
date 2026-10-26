"""Approve or reject a SellerApplication -- the reviewed path for public applicants.

This is how a member of the public becomes a seller. It is not the only way
seller access can be assigned: operators can still use the Django admin (in
the default deployment) and the `provision_seller` command. Accounts changed
that way are detected below and refused, never silently reconciled.

Errors are Django's own: `PermissionDenied` when the reviewer may not decide,
`ValidationError` (with a stable `code`) when the application or applicant is
in a state that cannot be decided. A missing application raises
`SellerApplication.DoesNotExist`. Nothing here depends on DRF, so the browser
views and any API can map these the same way.

Lock order, in every operation: SellerApplication row, then the applicant's
User row, then any Maker rows owned by the applicant. Approving the same
application concurrently therefore runs one request after the other; the
second sees the committed result.

Inconsistent records -- an applicant who is already a seller or already owns
a Maker, or an approved application whose Maker/role no longer line up -- are
refused with code "inconsistent_state" by both approval and rejection, for an
administrator to reconcile. They are never silently repaired.
"""
from __future__ import annotations

from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from products.models import Maker

from .models import SellerApplication, User

Status = SellerApplication.Status
REVIEW_NOTE_MAX_LENGTH = SellerApplication._meta.get_field("review_note").max_length


def _require_reviewer(reviewer) -> None:
    """Active administrator per the current database row, not the caller's copy."""
    if reviewer is None or not getattr(reviewer, "is_authenticated", False) or reviewer.pk is None:
        raise PermissionDenied("Only an administrator can review seller applications.")
    authorised = (User.objects.filter(pk=reviewer.pk, is_active=True)
                  .filter(Q(is_admin=True) | Q(is_superuser=True)).exists())
    if not authorised:
        raise PermissionDenied("Only an administrator can review seller applications.")


def require_reviewer(reviewer) -> None:
    """Public form of the reviewer check, so review pages gate on the same rule."""
    _require_reviewer(reviewer)


def _lock_for_review(application_id, reviewer):
    """Authorise, then lock the application and its applicant in the fixed order."""
    _require_reviewer(reviewer)
    application = SellerApplication.objects.select_for_update().get(pk=application_id)
    if application.user_id == reviewer.pk:
        raise PermissionDenied("You cannot review your own seller application.")
    applicant = User.objects.select_for_update().get(pk=application.user_id)
    owned_makers = list(Maker.objects.select_for_update().filter(owner=applicant).order_by("pk"))
    return application, applicant, owned_makers


def _inconsistent(message: str) -> ValidationError:
    return ValidationError(message, code="inconsistent_state")


@transaction.atomic
def approve_application(application_id, reviewer) -> SellerApplication:
    """Create the applicant's shop and grant seller access, exactly once.

    Re-approving an already-approved, consistent application returns it
    unchanged (same Maker, reviewer and review time; nothing written).
    """
    application, applicant, owned_makers = _lock_for_review(application_id, reviewer)

    if application.status == Status.APPROVED:
        maker = application.maker
        if not (maker is not None and maker.owner_id == applicant.pk and applicant.is_seller
                and [m.pk for m in owned_makers] == [maker.pk]):
            raise _inconsistent("This approved application no longer matches its seller account. "
                                "An administrator must reconcile it.")
        return application
    if application.status != Status.PENDING:
        raise ValidationError("Only a pending application can be approved.", code="not_pending")

    if not applicant.is_active:
        raise ValidationError("An inactive account cannot be approved as a seller.",
                              code="applicant_inactive")
    if applicant.is_seller or owned_makers:
        raise _inconsistent("This account already has a seller role or shop. "
                            "An administrator must reconcile it before approval.")

    maker = Maker.objects.create(
        owner=applicant,
        name=application.shop_name,
        slug="seller-" + uuid4().hex[:16],  # same convention as provision_seller
        discipline=application.discipline,
        location=application.location,
        short_bio=application.description,
        is_active=True,
    )
    applicant.is_seller = True
    applicant.save(update_fields=["is_seller", "updated_at"])

    application.status = Status.APPROVED
    application.maker = maker
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "maker", "reviewed_by", "reviewed_at", "updated_at"])
    return application


@transaction.atomic
def reject_application(application_id, reviewer, reason: str) -> SellerApplication:
    """Record a rejection with the reviewer's reason; grants nothing.

    Re-rejecting an already-rejected application returns it unchanged (the
    original reviewer, time and reason are kept). An approved application
    cannot be rejected. Either way, an applicant who has meanwhile become a
    seller or acquired a Maker by another route is refused as inconsistent,
    so the conflict is surfaced rather than recorded as a clean rejection.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Please give a reason for the rejection.", code="reason_required")
    if len(reason) > REVIEW_NOTE_MAX_LENGTH:
        raise ValidationError(f"The reason must be at most {REVIEW_NOTE_MAX_LENGTH} characters.",
                              code="reason_too_long")

    application, applicant, owned_makers = _lock_for_review(application_id, reviewer)

    if application.status == Status.APPROVED:
        raise ValidationError("Only a pending application can be rejected.", code="not_pending")
    if applicant.is_seller or owned_makers:
        raise _inconsistent("This account already has a seller role or shop. "
                            "An administrator must reconcile it before deciding this application.")
    if application.status == Status.REJECTED:
        return application
    if application.status != Status.PENDING:
        raise ValidationError("Only a pending application can be rejected.", code="not_pending")

    application.status = Status.REJECTED
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    application.review_note = reason
    application.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
    return application
