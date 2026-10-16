"""A minimal public surface: no admin, account, payment-webhook or generic API."""
from django.urls import include, path
from django.http import HttpResponse
from django.views.generic import RedirectView
from functools import partial


def public_error(request, exception=None, *, status=404):
    title = {400: "Invalid request", 403: "Access denied", 404: "Page not found",
             500: "Something went wrong"}[status]
    return HttpResponse(f'<!doctype html><html lang="en"><meta charset="utf-8">'
        f'<title>{title}</title><h1>{title}</h1>'
        '<p><a href="/seller/assistant/">Return to the team demo</a></p></html>', status=status)


handler400 = partial(public_error, status=400)
handler403 = partial(public_error, status=403)
handler404 = partial(public_error, status=404)
handler500 = partial(public_error, status=500)

urlpatterns = [
    path("seller/workbench/", include("sellerdesk.urls")),
    path("api/mini-store/v1/", include("sellerdesk.customer_urls")),
    path("customer/preview/", include("sellerdesk.preview_urls")),
    path("", RedirectView.as_view(url="/seller/assistant/", permanent=False)),
    path("seller/assistant/", include("concierge.urls")),
]
