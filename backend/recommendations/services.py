"""Multi-factor recommendation engine for the buyer storefront.

V2 keeps recommendation logic isolated inside this app and ranks products using
both user behaviour and explainable product similarity.

Product-factor priority (highest first):
1. category / item type
2. colour
3. price proximity
4. maker
5. materials
6. collection
7. finish
8. size

Each factor can contribute independently. Products matching several factors
receive an additional combination bonus, so strong multi-factor matches can
outrank weak single-factor matches.

Behaviour strength is applied on top of product similarity:
- paid purchase history: 5x
- wishlist/favourites: 3x
- active cart activity: 2x

Guests use recent views and their own session's bag; new visitors fall back to
popular available catalogue items. Sold-out and inactive products are never returned.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.db.models import Count, Q

from accounts.models import WishlistItem
from orders.models import CartItem, OrderItem, PaymentStatus
from products.models import Product, StockStatus, VariantGroup


AVAILABLE_STOCK = [
    StockStatus.IN_STOCK,
    StockStatus.LOW_STOCK,
    StockStatus.MADE_TO_ORDER,
]

# A same-category match must beat any other single product factor.
FACTOR_WEIGHTS = {
    "category": 14.0,
    "colour": 7.0,
    "price": 4.0,
    "maker": 3.5,
    "materials": 3.0,
    "collection": 2.5,
    "finish": 1.5,
    "size": 0.75,
}

BEHAVIOUR_WEIGHTS = {
    "purchase history": 5.0,
    "wishlist": 3.0,
    "cart activity": 2.0,
    "recently viewed": 1.0,
}

RECENT_VIEWS_KEY = "recommendation_recent_views"
MAX_RECENT_VIEWS = 12


def record_product_view(request, product: Product) -> None:
    """Keep a small, deduplicated browsing history in the visitor's own session."""
    if request.method != "GET" or request.user.is_authenticated:
        return
    recent = request.session.get(RECENT_VIEWS_KEY, [])
    recent = [pk for pk in recent if type(pk) is int and pk != product.pk]
    request.session[RECENT_VIEWS_KEY] = (recent + [product.pk])[-MAX_RECENT_VIEWS:]


@dataclass(frozen=True)
class Recommendation:
    product: Product
    score: float
    reasons: tuple[str, ...]
    factor_scores: tuple[tuple[str, float], ...] = ()


def _candidate_queryset():
    return (
        Product.objects.active()
        .with_related()
        .filter(stock_status__in=AVAILABLE_STOCK)
    )


def _normalise_values(values: Iterable[str]) -> set[str]:
    return {str(v).strip().lower() for v in values if str(v).strip()}


def _variant_labels(product: Product, group: str) -> set[str]:
    """Active variant labels for one option axis, using prefetched variants."""
    return {
        variant.label.strip().lower()
        for variant in product.product_variants.all()
        if variant.is_active and variant.group == group and variant.label.strip()
    }


def _price_score(source: Product, candidate: Product) -> tuple[float, str | None]:
    """Smooth price similarity with a maximum contribution of 4 points."""
    high = max(source.price, candidate.price)
    if high <= 0:
        return 0.0, None

    relative_gap = abs(source.price - candidate.price) / high
    if relative_gap <= Decimal("0.10"):
        return FACTOR_WEIGHTS["price"], "very similar price"
    if relative_gap <= Decimal("0.20"):
        return 3.2, "similar price"
    if relative_gap <= Decimal("0.35"):
        return 2.2, "nearby price range"
    if relative_gap <= Decimal("0.50"):
        return 1.0, "broadly similar price"
    return 0.0, None


def _product_similarity(
    source: Product,
    candidate: Product,
) -> tuple[float, list[str], dict[str, float]]:
    """Return total score, explanations and per-factor score contributions.

    Factors are independent: a candidate can enter the ranking through category,
    colour, price or any other factor on its own. When several factors match, a
    combination bonus rewards the stronger overall fit.
    """
    factors: dict[str, float] = {}
    reasons: list[str] = []

    # 1) Item type / category -- deliberately the strongest single factor.
    if source.category_id == candidate.category_id:
        factors["category"] = FACTOR_WEIGHTS["category"]
        reasons.append("same category")

    # 2) Colour -- the second-most important product factor.
    source_colours = _variant_labels(source, VariantGroup.COLOUR)
    candidate_colours = _variant_labels(candidate, VariantGroup.COLOUR)
    colour_overlap = source_colours & candidate_colours
    if colour_overlap:
        # One common colour is already meaningful; two or more reaches full weight.
        factors["colour"] = min(
            FACTOR_WEIGHTS["colour"],
            5.5 + 1.5 * max(0, len(colour_overlap) - 1),
        )
        colour_names = ", ".join(sorted(colour_overlap)[:3])
        reasons.append(f"shared colour: {colour_names}")

    # 3) Price proximity.
    price_score, price_reason = _price_score(source, candidate)
    if price_score:
        factors["price"] = price_score
        if price_reason:
            reasons.append(price_reason)

    # 4) Same maker / artisan.
    if source.maker_id == candidate.maker_id:
        factors["maker"] = FACTOR_WEIGHTS["maker"]
        reasons.append("same maker")

    # 5) Material-family overlap. This catches e.g. different stoneware strings.
    source_materials = _normalise_values(source.material_families)
    candidate_materials = _normalise_values(candidate.material_families)
    material_overlap = source_materials & candidate_materials
    if material_overlap:
        factors["materials"] = min(
            FACTOR_WEIGHTS["materials"],
            2.25 + 0.75 * max(0, len(material_overlap) - 1),
        )
        reasons.append("similar materials")

    # 6) Editorial collection overlap.
    source_collections = {c.pk for c in source.collections.all()}
    candidate_collections = {c.pk for c in candidate.collections.all()}
    collection_overlap = source_collections & candidate_collections
    if collection_overlap:
        factors["collection"] = min(
            FACTOR_WEIGHTS["collection"],
            1.75 + 0.75 * max(0, len(collection_overlap) - 1),
        )
        reasons.append("shared collection")

    # 7) Finish variants.
    finish_overlap = (
        _variant_labels(source, VariantGroup.FINISH)
        & _variant_labels(candidate, VariantGroup.FINISH)
    )
    if finish_overlap:
        factors["finish"] = FACTOR_WEIGHTS["finish"]
        reasons.append("similar finish")

    # 8) Size overlap -- useful, but intentionally weaker than style factors.
    size_overlap = (
        _variant_labels(source, VariantGroup.SIZE)
        & _variant_labels(candidate, VariantGroup.SIZE)
    )
    if size_overlap:
        factors["size"] = FACTOR_WEIGHTS["size"]
        reasons.append("similar size option")

    # Reward genuine combinations while preserving category as the strongest
    # individual factor. A combination can still beat a category-only match.
    matched_factor_count = len(factors)
    if matched_factor_count >= 5:
        factors["combination"] = 4.0
        reasons.append("strong multi-factor match")
    elif matched_factor_count >= 3:
        factors["combination"] = 2.0
        reasons.append("multi-factor match")

    score = round(sum(factors.values()), 3)
    return score, reasons, factors


def popular_products(
    limit: int = 8,
    *,
    exclude_ids: Iterable[int] = (),
) -> list[Recommendation]:
    """Cold-start fallback based on purchases, carts and wishlists."""
    exclude_ids = list(exclude_ids)
    products = list(
        _candidate_queryset()
        .exclude(pk__in=exclude_ids)
        .annotate(
            purchase_count=Count(
                "order_items",
                filter=Q(order_items__order__payment_status=PaymentStatus.PAID),
                distinct=True,
            ),
            wishlist_count=Count("wishlisted_by", distinct=True),
            cart_count=Count("cart_items", distinct=True),
        )
        .order_by(
            "-purchase_count",
            "-wishlist_count",
            "-cart_count",
            "-is_featured",
            "-sort_weight",
            "-created_at",
        )[:limit]
    )
    return [Recommendation(p, 0.0, ("popular",), ()) for p in products]


def similar_products(product: Product, limit: int = 8) -> list[Recommendation]:
    """Explainable item-to-item recommendations using all product factors."""
    candidates = list(_candidate_queryset().exclude(pk=product.pk))
    ranked: list[Recommendation] = []

    for candidate in candidates:
        score, reasons, factors = _product_similarity(product, candidate)
        if score <= 0:
            continue
        ranked.append(
            Recommendation(
                candidate,
                score,
                tuple(reasons),
                tuple(sorted(factors.items(), key=lambda item: item[1], reverse=True)),
            )
        )

    ranked.sort(
        key=lambda item: (
            item.score,
            item.product.is_featured,
            item.product.sort_weight,
            item.product.created_at,
        ),
        reverse=True,
    )

    if len(ranked) < limit:
        existing = {product.pk, *(r.product.pk for r in ranked)}
        ranked.extend(popular_products(limit - len(ranked), exclude_ids=existing))
    return ranked[:limit]


def recommendations_for_user(user, limit: int = 8) -> list[Recommendation]:
    """Personalised hybrid ranking over purchase, wishlist and cart seeds.

    Every interacted product becomes a seed. Product-factor scores are multiplied
    by behaviour strength and accumulated, allowing both repeated preferences and
    different factors to combine naturally.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return popular_products(limit)

    purchase_rows = list(
        OrderItem.objects.filter(
            order__user=user,
            order__payment_status=PaymentStatus.PAID,
            product__isnull=False,
        )
        .select_related("product", "product__category", "product__maker")
        .prefetch_related("product__collections", "product__product_variants")
        .order_by("-order__placed_at")[:50]
    )
    wishlist_rows = list(
        WishlistItem.objects.filter(user=user, product__is_active=True)
        .select_related("product", "product__category", "product__maker")
        .prefetch_related("product__collections", "product__product_variants")[:30]
    )
    cart_rows = list(
        CartItem.objects.filter(
            cart__user=user,
            cart__is_active=True,
            product__is_active=True,
        )
        .select_related("product", "product__category", "product__maker")
        .prefetch_related("product__collections", "product__product_variants")[:30]
    )

    seeds: list[tuple[Product, float, str]] = []
    seeds.extend(
        (row.product, BEHAVIOUR_WEIGHTS["purchase history"], "purchase history")
        for row in purchase_rows
        if row.product
    )
    seeds.extend(
        (row.product, BEHAVIOUR_WEIGHTS["wishlist"], "wishlist")
        for row in wishlist_rows
    )
    seeds.extend(
        (row.product, BEHAVIOUR_WEIGHTS["cart activity"], "cart activity")
        for row in cart_rows
    )

    if not seeds:
        return popular_products(limit)

    purchased_ids = {row.product_id for row in purchase_rows if row.product_id}
    return _rank_from_seeds(seeds, limit, exclude_ids=purchased_ids)


def recommendations_for_guest(session=None, limit: int = 8) -> list[Recommendation]:
    """Use only server-owned session history and that session's anonymous bag."""
    if session is None:
        return popular_products(limit)

    recent_ids = [
        pk for pk in session.get(RECENT_VIEWS_KEY, []) if type(pk) is int
    ][-MAX_RECENT_VIEWS:]
    recent = Product.objects.active().with_related().filter(pk__in=recent_ids)
    seeds = [(p, BEHAVIOUR_WEIGHTS["recently viewed"], "recently viewed") for p in recent]
    if session.session_key:
        cart_rows = (
            CartItem.objects.filter(
                cart__session_key=session.session_key,
                cart__user__isnull=True,
                cart__is_active=True,
                product__is_active=True,
            )
            .select_related("product", "product__category", "product__maker")
            .prefetch_related("product__collections", "product__product_variants")[:30]
        )
        seeds.extend(
            (row.product, BEHAVIOUR_WEIGHTS["cart activity"], "cart activity")
            for row in cart_rows
        )
    if not seeds:
        return popular_products(limit)
    return _rank_from_seeds(seeds, limit, exclude_ids={p.pk for p, _, _ in seeds})


def _rank_from_seeds(
    seeds: Iterable[tuple[Product, float, str]],
    limit: int,
    *,
    exclude_ids: Iterable[int],
) -> list[Recommendation]:
    """Share the same product-factor ranking for account and guest signals."""
    candidate_map = {
        product.pk: product
        for product in _candidate_queryset().exclude(pk__in=exclude_ids)
    }

    scores: defaultdict[int, float] = defaultdict(float)
    reasons: defaultdict[int, Counter[str]] = defaultdict(Counter)
    factor_scores: defaultdict[int, defaultdict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )

    for seed, behaviour_weight, signal_name in seeds:
        for candidate_id, candidate in candidate_map.items():
            if candidate_id == seed.pk:
                continue

            similarity, similarity_reasons, factors = _product_similarity(seed, candidate)
            if similarity <= 0:
                continue

            weighted_similarity = behaviour_weight * similarity
            scores[candidate_id] += weighted_similarity
            reasons[candidate_id][signal_name] += behaviour_weight

            for reason in similarity_reasons:
                reasons[candidate_id][reason] += behaviour_weight

            for factor_name, factor_score in factors.items():
                factor_scores[candidate_id][factor_name] += behaviour_weight * factor_score

    ranked_ids = sorted(
        scores,
        key=lambda pk: (
            scores[pk],
            candidate_map[pk].is_featured,
            candidate_map[pk].sort_weight,
            candidate_map[pk].created_at,
        ),
        reverse=True,
    )

    ranked = [
        Recommendation(
            candidate_map[pk],
            round(scores[pk], 3),
            tuple(reason for reason, _ in reasons[pk].most_common(5)),
            tuple(
                (factor, round(value, 3))
                for factor, value in sorted(
                    factor_scores[pk].items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ),
        )
        for pk in ranked_ids[:limit]
    ]

    if len(ranked) < limit:
        existing_ids = set(exclude_ids) | {r.product.pk for r in ranked}
        ranked.extend(popular_products(limit - len(ranked), exclude_ids=existing_ids))

    return ranked[:limit]


def recommend(
    *,
    user=None,
    product: Product | None = None,
    session=None,
    limit: int = 8,
) -> list[Recommendation]:
    limit = max(1, min(int(limit or 8), 24))
    if product is not None:
        return similar_products(product, limit)
    if not user or not getattr(user, "is_authenticated", False):
        return recommendations_for_guest(session, limit)
    return recommendations_for_user(user, limit)
