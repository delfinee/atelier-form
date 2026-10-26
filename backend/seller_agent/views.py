from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, FileResponse
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_GET
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie


@login_required
@ensure_csrf_cookie
def desk(request):
    if not settings.SELLER_AGENT_ENABLED:
        raise Http404
    template = "seller_agent/demo_desk.html" if getattr(settings, "SELLER_PUBLIC_DEMO", False) else "seller_agent/desk.html"
    return render(request, template, {"mode":"web", "csrf_cookie_name":settings.CSRF_COOKIE_NAME,
        "phone_preview":getattr(settings, "SELLER_PHONE_PREVIEW", False),
        "public_demo":getattr(settings, "SELLER_PUBLIC_DEMO", False),
        "seller_only":getattr(settings, "SELLER_PHONE_PREVIEW", False) or getattr(settings, "SELLER_PRODUCTION", False) or getattr(settings, "SELLER_PUBLIC_DEMO", False)})


@ensure_csrf_cookie
def link(request):
    if not settings.SELLER_AGENT_ENABLED:
        raise Http404
    return render(request, "seller_agent/link.html", {"csrf_cookie_name":settings.CSRF_COOKIE_NAME})


@ensure_csrf_cookie
def mini_preview(request):
    if not settings.SELLER_AGENT_ENABLED:
        raise Http404
    return render(request, "seller_agent/desk.html", {"mode":"mini", "csrf_cookie_name":settings.CSRF_COOKIE_NAME})


@login_required
@require_GET
def download_bundle(request):
    from .services import has_shop
    if not has_shop(request.user):
        raise PermissionDenied
    path = settings.BASE_DIR / '.seller-agent-runtime' / 'delivery' / 'Atelier-Form-Seller-WeChat.zip'
    if not path.is_file():
        raise Http404('The source bundle is not installed on this host.')
    response = FileResponse(path.open('rb'), as_attachment=True, filename=path.name, content_type='application/zip')
    response['Cache-Control'] = 'private, no-store'
    return response
