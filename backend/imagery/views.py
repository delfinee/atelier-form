"""Serving photographs out of PostgreSQL, and the credits they oblige us to show."""

from __future__ import annotations

from django.http import Http404, HttpResponse, HttpResponseNotModified
from django.shortcuts import render
from django.views.decorators.http import require_safe

from .models import SiteImage

# A year. Safe because `resolver.image_url` appends the checksum as `?v=`, so
# changed bytes are a different URL rather than a stale cache entry.
MAX_AGE = 60 * 60 * 24 * 365


@require_safe
def site_image(request, name: str):
    """Stream one stored image.

    `with_data()` is the only query in the codebase that selects the bytea
    column, and it is answered straight from the conditional-request headers
    whenever the browser already holds the file.
    """
    try:
        image = SiteImage.objects.with_data().get(name=name)
    except SiteImage.DoesNotExist:
        raise Http404(f"No stored image named {name!r}")

    etag = f'"{image.checksum}"'
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponseNotModified()
        response["ETag"] = etag
        return response

    response = HttpResponse(bytes(image.data), content_type=image.content_type)
    response["ETag"] = etag
    # Content-Length is left to Django, which measures the body it is actually
    # sending. Asserting `byte_size` here meant that a row whose stored length
    # had drifted from its stored bytes served a truncated or over-long
    # response, which a browser renders as an empty box.
    response["Cache-Control"] = f"public, max-age={MAX_AGE}, immutable"
    # Stops a stored JPEG from ever being sniffed as something executable.
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_safe
def credits(request):
    """Attribution for every image whose licence requires it.

    Most of the catalogue photography is Creative Commons rather than public
    domain, and CC BY / BY-SA are only honoured if the credit is actually
    published. This page is that compliance, not decoration.
    """
    images = SiteImage.objects.exclude(license="").order_by("creator", "name")
    credited = [img for img in images if img.needs_attribution]
    public_domain = [img for img in images if not img.needs_attribution]
    return render(request, "imagery/credits.html", {
        "credited": credited,
        "public_domain": public_domain,
        "title": "Image Credits",
        "meta_title": "Image Credits — Atelier Form",
    })
