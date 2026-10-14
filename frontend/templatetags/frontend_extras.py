"""Template helpers for the frontend."""

from __future__ import annotations

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe
from django.utils.translation import gettext

from frontend.catalogue_i18n import (
    localize_colour_label, localize_delivery_label, localize_order_date,
    localize_order_estimated, localize_order_item_name, localize_order_item_variant,
    localize_order_status, localize_order_timeline, localize_payment_status,
    localize_size_label,
)
from imagery.models import RATIOS as PIXEL_RATIOS
from imagery.resolver import image_url

register = template.Library()

# The CSS boxes are derived from the pixel dimensions `imagery` crops to, so a
# photograph can never be encoded to one shape and reserved space in another.
RATIOS = {name: f"{width} / {height}" for name, (width, height) in PIXEL_RATIOS.items()}


@register.simple_tag
def placeholder(name: str) -> str:
    """URL for a named image.

    Resolves to the photograph stored in PostgreSQL under this name, or to the
    generated SVG placeholder while that slot is still unphotographed. The tag
    name is unchanged so no template had to be touched.
    """
    return image_url(name)


@register.simple_tag
def ratio(name: str) -> str:
    return RATIOS.get(name, "4 / 5")


@register.filter
def money(value) -> str:
    """Format a price. The symbol comes from settings, so switching to RMB is
    an environment change rather than a code change."""
    from decimal import Decimal, InvalidOperation

    try:
        amount = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return ""
    whole = f"{amount:,.2f}".rstrip("0").rstrip(".")
    return f"{settings.COMMERCE['CURRENCY_SYMBOL']}{whole}"


@register.filter
def material_families(product) -> list[str]:
    return product.material_families


@register.filter
def colour_variants(variants) -> list:
    return [v for v in variants if v.group == "colour"]


@register.filter
def size_variants(variants) -> list:
    return [v for v in variants if v.group == "size"]


@register.simple_tag
def colour_label(label: str) -> str:
    return localize_colour_label(label)


@register.simple_tag
def size_label(label: str) -> str:
    return localize_size_label(label)


@register.simple_tag
def order_status(label):
    return localize_order_status(label)


@register.simple_tag
def payment_status(label):
    return localize_payment_status(label)


@register.simple_tag
def delivery_label(label):
    return localize_delivery_label(label)


@register.simple_tag
def order_item_name(item):
    return localize_order_item_name(item)


@register.simple_tag
def order_item_variant(item):
    return localize_order_item_variant(item)


@register.simple_tag
def order_date(order):
    return localize_order_date(order)


@register.simple_tag
def order_estimated(order):
    return localize_order_estimated(order)


@register.simple_tag
def order_timeline(order):
    return localize_order_timeline(order)


@register.simple_tag
def stock_label(status: str) -> str:
    label = {"in-stock": "In stock", "low-stock": "Low stock",
             "made-to-order": "Made to order"}.get(status)
    return gettext(label) if label else ""


@register.simple_tag(takes_context=True)
def query_toggle(context, key: str, value: str) -> str:
    """Return the current querystring with `value` toggled in the `key` facet.

    Lets the filter UI work without JavaScript -- the JS layer only enhances it.
    """
    request = context["request"]
    params = request.GET.copy()
    existing = params.getlist(key)
    if value in existing:
        existing.remove(value)
    else:
        existing.append(value)
    params.setlist(key, existing)
    params.pop("page", None)
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs) -> str:
    request = context["request"]
    params = request.GET.copy()
    for key, value in kwargs.items():
        params[key] = value
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"


@register.simple_tag
def icon(name: str, size: int = 20) -> str:
    """Inline stroke icons. Kept as a single set so weight stays consistent."""
    paths = {
        "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
        "bag": '<path d="M6 8h12l-1 12H7L6 8Z"/><path d="M9.5 8V6a2.5 2.5 0 0 1 5 0v2"/>',
        "user": '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c0-3.6 3.1-5.5 7-5.5s7 1.9 7 5.5"/>',
        "heart": '<path d="M12 20s-7-4.4-7-9.2A3.9 3.9 0 0 1 12 8a3.9 3.9 0 0 1 7 2.8C19 15.6 12 20 12 20Z"/>',
        "close": '<path d="M6 6l12 12M18 6L6 18"/>',
        "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
        "minus": '<path d="M5 12h14"/>',
        "plus": '<path d="M12 5v14M5 12h14"/>',
        "chevron-down": '<path d="M6 9.5l6 6 6-6"/>',
        "chevron-right": '<path d="M9.5 6l6 6-6 6"/>',
        "chevron-left": '<path d="M14.5 6l-6 6 6 6"/>',
        "arrow-right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
        "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
        "filter": '<path d="M4 7h16M7 12h10M10 17h4"/>',
        "trash": '<path d="M5 7h14M10 7V5h4v2M7 7l1 13h8l1-13"/>',
        "zoom": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5M8.5 11h5M11 8.5v5"/>',
        "alert": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.2v.3"/>',
        "chat": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
        "sparkles": '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>',
    }
    return mark_safe(
        f'<svg class="icon" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="1.4" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true" focusable="false">{paths.get(name, "")}</svg>'
    )


# The frontend ships exactly two languages, so the header offers a switch
# rather than a menu: the button shows the language you are reading and one tap
# swaps to the other.
LANGUAGES = {
    "en": {"label": "EN", "tag": "en"},
    "zh-hans": {"label": "中文", "tag": "zh-Hans"},
}


@register.simple_tag
def language_toggle() -> dict:
    """Everything the header switch needs: what you are reading, and the swap."""
    from django.utils.translation import get_language, gettext

    # `get_language()` returns the negotiated code, which may be a regional
    # variant such as "en-us"; the switch only cares which of the two it is.
    current = "zh-hans" if (get_language() or "").lower().startswith("zh") else "en"
    target = "en" if current == "zh-hans" else "zh-hans"
    return {
        "current_code": current,
        "current_label": LANGUAGES[current]["label"],
        "current_tag": LANGUAGES[current]["tag"],
        "target_code": target,
        "target_label": LANGUAGES[target]["label"],
        # Describes what the button does, for the tooltip and screen readers --
        # the visible label alone ("EN") does not say what a click will do.
        "action": (gettext("Switch to English") if target == "en"
                   else gettext("Switch to Chinese")),
    }
