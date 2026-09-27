"""Public recommendation API."""

from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from products.models import Product
from products.serializers import ProductListSerializer

from .services import recommend


@extend_schema(
    summary="Recommended products",
    description=(
        "Returns personalised multi-factor recommendations for the current user. "
        "Pass ?product=<slug> for content-similar recommendations. "
        "Anonymous/new users fall back to popular available products. "
        "Each result includes an explainable factor-score breakdown."
    ),
    responses=ProductListSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([AllowAny])
def recommendations(request):
    raw_limit = request.query_params.get("limit", "8")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = 8

    product = None
    product_slug = (request.query_params.get("product") or "").strip()
    if product_slug:
        product = Product.objects.active().with_related().filter(slug=product_slug).first()
        if product is None:
            return Response({"detail": "Unknown product."}, status=404)

    ranked = recommend(user=request.user, product=product, limit=limit)
    serializer = ProductListSerializer(
        [item.product for item in ranked], many=True, context={"request": request}
    )

    recommendation_meta = {
        str(item.product.uuid): {
            "score": item.score,
            "reasons": list(item.reasons),
            "factors": {name: score for name, score in item.factor_scores},
        }
        for item in ranked
    }

    data = []
    for row in serializer.data:
        enriched = dict(row)
        meta = recommendation_meta.get(
            str(row.get("uuid")),
            {"score": 0.0, "reasons": [], "factors": {}},
        )
        enriched["recommendation_score"] = meta["score"]
        enriched["recommendation_reasons"] = meta["reasons"]
        enriched["recommendation_factors"] = meta["factors"]
        data.append(enriched)

    return Response({"count": len(data), "results": data})
