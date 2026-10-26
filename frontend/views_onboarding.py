"""Public seller onboarding: the "Sell with us" page and the applicant's own
application form and status.

Submitting an application grants nothing. Seller access and the shop are
created only when an administrator approves it through
accounts.seller_onboarding. An account whose seller role and shop do not line
up is shown a notice and left for an administrator; it is never repaired here.
"""
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods

from accounts.models import SellerApplication
from products.models import Maker

from .forms_onboarding import SellerApplicationForm
from .mockdata.content import SITE

SELLER = "seller"              # a consistent, active seller account
INCONSISTENT = "inconsistent"  # role and shop disagree; an administrator must reconcile
NONE = "none"                  # an ordinary buyer account


def _seller_state(user) -> str:
    maker = Maker.objects.filter(owner=user).first()
    if user.is_seller and maker is not None and maker.is_active:
        return SELLER
    if user.is_seller or maker is not None:
        return INCONSISTENT
    return NONE


@require_GET
def sell_landing(request):
    apply_url = reverse("seller_application")
    state = application = None
    if request.user.is_authenticated:
        state = _seller_state(request.user)
        application = SellerApplication.objects.filter(user=request.user).first()
    return render(request, "frontend/onboarding/landing.html", {
        "state": state,
        "application": application,
        "apply_url": apply_url,
        "register_url": f"{reverse('register')}?next={quote(apply_url)}",
        "login_url": f"{reverse('login')}?next={quote(apply_url)}",
        "meta_title": f"{_('Sell with us')} — {SITE['brand']}",
    })


@login_required
@require_http_methods(["GET", "POST"])
def seller_application(request):
    user = request.user
    state = _seller_state(user)
    if state == SELLER:
        return redirect("seller_product_list")

    application = SellerApplication.objects.filter(user=user).first()
    context = {"application": application, "form": None, "inconsistent": False,
               "current_path": reverse("seller_application"),
               "meta_title": f"{_('Seller application')} — {SITE['brand']}"}

    # An approved application should mean a consistent seller (handled above).
    if state == INCONSISTENT or (application and application.status == SellerApplication.Status.APPROVED):
        context["inconsistent"] = True
        return render(request, "frontend/onboarding/application.html", context)

    if application is not None:
        if request.method == "POST":
            messages.info(request, _("You have already applied. Your application's status is below."))
            return redirect("seller_application")
        return render(request, "frontend/onboarding/application.html", context)

    form = SellerApplicationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        new_application = form.save(commit=False)
        new_application.user = user
        try:
            with transaction.atomic():
                new_application.save()
        except IntegrityError:  # a simultaneous submission for this account won
            messages.info(request, _("You have already applied. Your application's status is below."))
        else:
            messages.success(request, _("Thank you. Your application has been sent for review."))
        return redirect("seller_application")

    context["form"] = form
    return render(request, "frontend/onboarding/application.html", context)
