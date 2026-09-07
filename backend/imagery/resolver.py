"""The one place that decides what URL an image name resolves to.

Templates, DRF serializers and model properties all call `image_url`, so a
photograph appearing in PostgreSQL swaps every surface at once, and a name with
no row yet still renders its generated SVG instead of a broken image. That
graceful fallback is what lets the catalogue be photographed incrementally.
"""

from __future__ import annotations

from django.core.cache import cache
from django.db.utils import Error as DatabaseError
from django.templatetags.static import static
from django.urls import reverse

# Generated SVG placeholders, still the fallback for any name not yet fetched.
PLACEHOLDER_PREFIX = "frontend/img/placeholders"

_CACHE_KEY = "imagery:index:v1"
_CACHE_TTL = 300


def _index() -> dict[str, str]:
    """`{name: checksum}` for every stored photograph.

    A page renders dozens of images; one cached map keeps that to a single
    small query instead of one lookup per `<img>`. `data` is deferred by the
    default manager, so this never touches the bytes.
    """
    index = cache.get(_CACHE_KEY)
    if index is None:
        from .models import SiteImage

        try:
            index = dict(SiteImage.objects.values_list("name", "checksum"))
        except DatabaseError:
            # Before `migrate` has created the table -- fall back to SVGs
            # rather than taking the whole site down.
            return {}
        cache.set(_CACHE_KEY, index, _CACHE_TTL)
    return index


# With the default per-process cache, a freshly fetched image can take up to
# _CACHE_TTL to appear in workers other than the one that stored it. The cost of
# that window is one more request served from the SVG fallback, so it is not
# worth a shared cache backend until there is one for other reasons.


def invalidate_index() -> None:
    cache.delete(_CACHE_KEY)


def image_url(name: str) -> str:
    """Photograph URL if one is stored, otherwise the generated placeholder."""
    if not name:
        return ""
    checksum = _index().get(name)
    if not checksum:
        return static(f"{PLACEHOLDER_PREFIX}/{name}.svg")
    # The version token makes the URL change whenever the bytes do, which is
    # what allows the response to be cached immutably for a year.
    return f"{reverse('site_image', args=[name])}?v={checksum[:12]}"


def has_photo(name: str) -> bool:
    return bool(name) and name in _index()
