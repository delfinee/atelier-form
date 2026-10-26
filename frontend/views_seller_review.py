"""Administrator review of seller applications, under /staff/seller-applications/.

These pages display applications and hand decisions to
accounts.seller_onboarding, which authorises the reviewer again, locks the rows
and makes every change. Nothing here creates a shop, grants or revokes the
seller role, or writes an application's decision, and inconsistent accounts are
shown, never repaired.

Anyone who is not an active administrator (by the current database row, the
same rule as the service) gets a 404 on every route, before any application is
looked up, so neither the pages nor the applications are disclosed.
"""
from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _, gettext_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe

from accounts import seller_onboarding
from accounts.models import SellerApplication
from products.models import Maker

from .forms_onboarding import SellerRejectionForm
from .mockdata.content import SITE

Status = SellerApplication.Status
PAGE_SIZE = 25

DECISION_ERRORS = {
    "not_pending": gettext_lazy("This application has already been decided, so that decision "
                                "can't be made. Nothing was changed."),
    "applicant_inactive": gettext_lazy("The applicant's account is inactive, so it can't be "
                                       "approved. Nothing was changed."),
    "inconsistent_state": gettext_lazy("The applicant's seller role or shop doesn't match this "
                                       "application. Nothing was changed: reconcile the account "
                                       "by hand first."),
    "reason_required": gettext_lazy("Please give a reason for the rejection."),
    "reason_too_long": gettext_lazy("The reason is too long."),
}


def reviewer_only(view):
    """404 unless the signed-in account is currently an active administrator."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            seller_onboarding.require_reviewer(request.user)
        except PermissionDenied:
            raise Http404
        return view(request, *args, **kwargs)
    return wrapped


def _status_filters(current):
    counts = dict(SellerApplication.objects.order_by().values_list("status")
                  .annotate(n=Count("pk")))
    labels = ((Status.PENDING, _("Pending")), (Status.APPROVED, _("Approved")),
              (Status.REJECTED, _("Rejected")))
    return [{"value": value, "label": label, "count": counts.get(value, 0),
             "current": value == current} for value, label in labels]


@never_cache
@reviewer_only
@require_safe
def application_list(request):
    status = request.GET.get("status")
    if status not in Status.values:
        status = Status.PENDING
    # The queue is worked oldest first; decided applications show the latest decision first.
    ordering = ("created_at", "pk") if status == Status.PENDING else ("-reviewed_at", "-pk")
    applications = (SellerApplication.objects.filter(status=status)
                    .select_related("user").order_by(*ordering))
    page = Paginator(applications, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "frontend/staff/seller_applications/list.html", {
        "status": status,
        "filters": _status_filters(status),
        "page_obj": page,
        "meta_title": f"{_('Seller applications')} — {SITE['brand']}",
    })


def _consistency_problems(application, applicant, owned_makers):
    """What the service would refuse as "inconsistent_state", for manual reconciliation.

    Display only: the service checks again under lock and stays the authority.
    """
    problems = []
    owned = [maker.pk for maker in owned_makers]
    if application.status == Status.APPROVED:
        maker = application.maker
        if maker is None or maker.owner_id != applicant.pk:
            problems.append(_("The shop linked to this application is not owned by the applicant."))
        if owned and (maker is None or owned != [maker.pk]):
            problems.append(_("The applicant owns a shop other than the one linked to this application."))
        if not applicant.is_seller:
            problems.append(_("The applicant no longer has the seller role."))
    else:
        if applicant.is_seller:
            problems.append(_("The applicant already has the seller role."))
        if owned:
            problems.append(_("The applicant already owns a shop."))
    return problems


def _render_detail(request, application, rejection_form):
    applicant = application.user
    owned_makers = list(Maker.objects.filter(owner=applicant).order_by("pk"))
    problems = _consistency_problems(application, applicant, owned_makers)
    own_application = application.user_id == request.user.pk
    decidable = application.status == Status.PENDING and not problems and not own_application
    return render(request, "frontend/staff/seller_applications/detail.html", {
        "application": application,
        "applicant": applicant,
        "owned_makers": owned_makers,
        "problems": problems,
        "own_application": own_application,
        "can_approve": decidable and applicant.is_active,
        "can_reject": decidable,
        "rejection_form": rejection_form,
        "meta_title": f"{application.shop_name} — {_('Seller applications')} — {SITE['brand']}",
    })


@never_cache
@reviewer_only
@require_safe
def application_detail(request, uuid):
    application = get_object_or_404(
        SellerApplication.objects.select_related("user", "reviewed_by", "maker"), uuid=uuid)
    return _render_detail(request, application, SellerRejectionForm())


def _decision_target(uuid):
    """(pk, applicant id, status) for the service call, or 404."""
    row = SellerApplication.objects.filter(uuid=uuid).values_list("pk", "user_id", "status").first()
    if row is None:
        raise Http404
    return row


def _refused(request, applicant_id):
    """The service refused this reviewer. Self-review is explained; anything else
    (for example, administrator rights removed mid-request) is hidden like any
    other unauthorised request."""
    if applicant_id != request.user.pk:
        raise Http404
    messages.error(request, _("You can't review your own application."))


def _decision_error(exc):
    return DECISION_ERRORS.get(getattr(exc, "code", None),
                               _("This decision couldn't be made. Nothing was changed."))


@never_cache
@reviewer_only
@require_POST
def application_approve(request, uuid):
    pk, applicant_id, status_before = _decision_target(uuid)
    try:
        seller_onboarding.approve_application(pk, request.user)
    except SellerApplication.DoesNotExist:
        raise Http404
    except PermissionDenied:
        _refused(request, applicant_id)
    except ValidationError as exc:
        messages.error(request, _decision_error(exc))
    else:
        if status_before == Status.APPROVED:
            messages.info(request, _("This application was already approved. Nothing was changed."))
        else:
            messages.success(request, _("Approved. The applicant now has a shop and seller access."))
    return redirect("staff_seller_application_detail", uuid=uuid)


@never_cache
@reviewer_only
@require_POST
def application_reject(request, uuid):
    pk, applicant_id, status_before = _decision_target(uuid)
    form = SellerRejectionForm(request.POST)
    if not form.is_valid():
        application = get_object_or_404(
            SellerApplication.objects.select_related("user", "reviewed_by", "maker"), pk=pk)
        return _render_detail(request, application, form)
    try:
        seller_onboarding.reject_application(pk, request.user, form.cleaned_data["reason"])
    except SellerApplication.DoesNotExist:
        raise Http404
    except PermissionDenied:
        _refused(request, applicant_id)
    except ValidationError as exc:
        messages.error(request, _decision_error(exc))
    else:
        if status_before == Status.REJECTED:
            messages.info(request, _("This application was already rejected. "
                                     "The original reason was kept."))
        else:
            messages.success(request, _("Rejected. The applicant can now see your reason."))
    return redirect("staff_seller_application_detail", uuid=uuid)
