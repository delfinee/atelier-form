"""Returns: the buyer's request form and the seller's returns queue.

Every rule (eligibility, quantities, refund limits, ownership) lives in
orders.returns; these views only scope lookups to the signed-in user and show
a rule the service rejects as a form error.
"""

from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from orders.models import Order, ReturnRequest, ReturnStatus
from orders.returns import (
    OPEN_STATUSES, decide_return, max_refund, request_return, return_eligibility_error,
    returnable_quantity,
)

from .forms_returns import ReturnDecisionForm, ReturnRequestForm
from .mockdata.content import SITE
from .views_seller import _get_seller_maker

# ?status= values on the seller returns page.
STATUS_FILTERS = {
    "open": OPEN_STATUSES,
    "all": None,
    **{value: (value,) for value in ReturnStatus.values},
}


# -- Buyer -----------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def account_return_request(request, order_id, item_id):
    # Scoped to the signed-in buyer: another customer's order or line 404s.
    order = Order.objects.filter(user=request.user, order_number=order_id).first()
    if order is None:
        raise Http404("Unknown order")
    item = get_object_or_404(order.items.select_related("product"), pk=item_id)

    blocked = return_eligibility_error(item)
    max_quantity = max(returnable_quantity(item), 1)
    form = None
    if not blocked:
        form = ReturnRequestForm(request.POST or None, request.FILES or None, max_quantity=max_quantity)
        if request.method == "POST" and form.is_valid():
            try:
                with transaction.atomic():
                    photo_name = ""
                    if form.photo_data:
                        from imagery.models import SiteImage
                        payload, width, height = form.photo_data
                        photo_name = "return-photo-" + uuid4().hex
                        SiteImage.objects.create(name=photo_name, data=payload, width=width,
                                                 height=height, content_type="image/jpeg",
                                                 provider="return-upload")
                    request_return(item, buyer=request.user, quantity=form.cleaned_data["quantity"],
                                   reason=form.cleaned_data["reason"],
                                   details=form.cleaned_data["details"], photo=photo_name)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, _("Your return request has been sent to the maker."))
                return redirect("account_order_detail", order_id=order.order_number)

    return render(request, "frontend/account/return_form.html", {
        "customer": request.user,
        "order": order,
        "item": item,
        "form": form,
        "blocked": blocked,
        "meta_title": f"{_('Return a piece')} — {SITE['brand']}",
    })


# -- Seller ----------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
def seller_returns(request):
    maker = _get_seller_maker(request)
    status_key = request.GET.get("status", "open")
    if status_key not in STATUS_FILTERS:
        status_key = "open"
    returns = (ReturnRequest.objects.filter(maker=maker)
               .select_related("order", "order_item", "buyer"))
    if STATUS_FILTERS[status_key] is not None:
        returns = returns.filter(status__in=STATUS_FILTERS[status_key])

    filters = [("open", _("Open")), ("all", _("All"))] + [
        (value, label) for value, label in ReturnStatus.choices]
    return render(request, "frontend/seller/returns.html", {
        "maker": maker,
        "returns": returns,
        "status_key": status_key,
        "filters": filters,
        "meta_title": f"{_('Returns')} — {maker.name}",
    })


@login_required
@require_http_methods(["GET", "POST"])
def seller_return_detail(request, uuid):
    maker = _get_seller_maker(request)
    # Scoped in the query: another seller's return 404s.
    return_request = get_object_or_404(
        ReturnRequest.objects.select_related("order", "order_item", "buyer"), uuid=uuid, maker=maker)

    form = ReturnDecisionForm(request.POST or None,
                              initial={"refund_amount": max_refund(return_request)})
    if request.method == "POST" and form.is_valid():
        try:
            decide_return(return_request, acting_maker=maker, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, _("Return updated. The buyer has been notified."))
            return redirect("seller_return_detail", uuid=return_request.uuid)

    return render(request, "frontend/seller/return_detail.html", {
        "maker": maker,
        "return_request": return_request,
        "order": return_request.order,
        "item": return_request.order_item,
        "form": form,
        "max_refund": max_refund(return_request),
        "meta_title": f"{_('Return')} {return_request.order.order_number} — {maker.name}",
    })
