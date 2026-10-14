from django import template
from django.utils.translation import gettext

from frontend.catalogue_i18n import localize_product
from recommendations.services import recommend

register = template.Library()


@register.inclusion_tag("frontend/components/recommendations.html", takes_context=True)
def recommendation_block(context, limit=4):
    request = context.get("request")
    if request is None:
        return {"recommendations": []}

    match = getattr(request, "resolver_match", None)
    url_name = getattr(match, "url_name", None)
    if url_name not in {"home", "product_detail"}:
        return {"recommendations": []}

    product = context.get("product") if url_name == "product_detail" else None
    ranked = recommend(user=request.user, product=product, limit=limit)
    return {
        "recommendations": [localize_product(item.product) for item in ranked],
        "recommendation_title": gettext("You may also like") if product else gettext("Recommended for you"),
        "recommendation_eyebrow": gettext("Based on this piece") if product else gettext("Picked for you"),
    }
