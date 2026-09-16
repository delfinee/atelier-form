from django import template

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
        "recommendations": [item.product for item in ranked],
        "recommendation_title": "You may also like" if product else "Recommended for you",
        "recommendation_eyebrow": "Based on this piece" if product else "Picked for you",
    }
