"""Recommendation engine for the buyer storefront.

The implementation intentionally stays inside this app so recommendation
strategy can evolve without coupling product/order/account business logic.

Signals used by the baseline hybrid ranker:
- purchase history (strongest)
- wishlist/favourites
- active cart activity
- product metadata similarity: category, maker, collections, materials, price

For anonymous/new users the service falls back to globally strong catalogue
items. Sold-out and inactive products are never returned.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.db.models import Count, Q

from accounts.models import WishlistItem
from orders.models import CartItem, OrderItem, PaymentStatus
from products.models import Product, StockStatus


AVAILABLE_STOCK = [
    StockStatus.IN_STOCK,
    StockStatus.LOW_STOCK,
    StockStatus.MADE_TO_ORDER,
]


@dataclass(frozen=True)
class Recommendation:
    product: Product
    score: float
    reasons: tuple[str, ...]


def _candidate_queryset():
    return (
        Product.objects.active()
        .with_related()
        .filter(stock_status__in=AVAILABLE_STOCK)
    )


def _normalise_materials(values: Iterable[str]) -> set[str]:
    return {str(v).strip().lower() for v in values if str(v).strip()}


def _product_similarity(source: Product, candidate: Product) -> tuple[float, list[str]]:
    """Content similarity using fields already available in the catalogue."""
    score = 0.0
    reasons: list[str] = []

    if source.category_id == candidate.category_id:
        score += 4.0
        reasons.append("same category")

    if source.maker_id == candidate.maker_id:
        score += 3.0
        reasons.append("same maker")

    source_collections = {c.pk for c in source.collections.all()}
    candidate_collections = {c.pk for c in candidate.collections.all()}
    overlap = source_collections & candidate_collections
    if overlap:
        score += min(3.0, 1.5 * len(overlap))
        reasons.append("shared collection")

    material_overlap = _normalise_materials(source.materials) & _normalise_materials(candidate.materials)
    if material_overlap:
        score += min(3.0, 1.0 * len(material_overlap))
        reasons.append("similar materials")

    high = max(source.price, candidate.price)
    if high > 0:
        relative_gap = abs(source.price - candidate.price) / high
        if relative_gap <= Decimal("0.20"):
            score += 1.5
            reasons.append("similar price")
        elif relative_gap <= Decimal("0.40"):
            score += 0.75

    return score, reasons


def popular_products(limit: int = 8, *, exclude_ids: Iterable[int] = ()) -> list[Recommendation]:
    """Cold-start fallback based on purchases, carts and wishlists.

    This is deliberately deterministic and does not require a trained model.
    Editorial flags are used only as tie-breakers when interaction counts are
    sparse, which keeps the endpoint useful on a fresh/demo database.
    """
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
    return [Recommendation(p, 0.0, ("popular",)) for p in products]


def similar_products(product: Product, limit: int = 8) -> list[Recommendation]:
    candidates = list(_candidate_queryset().exclude(pk=product.pk))
    ranked: list[Recommendation] = []
    for candidate in candidates:
        score, reasons = _product_similarity(product, candidate)
        if score > 0:
            ranked.append(Recommendation(candidate, score, tuple(reasons)))

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
    """Personalised hybrid recommendations for an authenticated user.

    Purchase history receives the greatest weight, followed by wishlist and
    cart activity. Those seed products are expanded through content similarity.
    Products already purchased are excluded from the normal personalised list;
    the fallback can still surface unseen popular products when history is
    sparse.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return popular_products(limit)

    purchase_rows = list(
        OrderItem.objects.filter(order__user=user, order__payment_status=PaymentStatus.PAID,
                                 product__isnull=False)
        .select_related("product", "product__category", "product__maker")
        .prefetch_related("product__collections")
        .order_by("-order__placed_at")[:50]
    )
    wishlist_rows = list(
        WishlistItem.objects.filter(user=user, product__is_active=True)
        .select_related("product", "product__category", "product__maker")
        .prefetch_related("product__collections")[:30]
    )
    cart_rows = list(
        CartItem.objects.filter(cart__user=user, cart__is_active=True, product__is_active=True)
        .select_related("product", "product__category", "product__maker")
        .prefetch_related("product__collections")[:30]
    )

    seeds: list[tuple[Product, float, str]] = []
    seeds.extend((row.product, 5.0, "purchase history") for row in purchase_rows if row.product)
    seeds.extend((row.product, 3.0, "wishlist") for row in wishlist_rows)
    seeds.extend((row.product, 2.0, "cart activity") for row in cart_rows)

    if not seeds:
        return popular_products(limit)

    purchased_ids = {row.product_id for row in purchase_rows if row.product_id}
    candidate_map = {p.pk: p for p in _candidate_queryset().exclude(pk__in=purchased_ids)}
    scores: defaultdict[int, float] = defaultdict(float)
    reasons: defaultdict[int, Counter[str]] = defaultdict(Counter)

    for seed, seed_weight, signal_name in seeds:
        for candidate_id, candidate in candidate_map.items():
            if candidate_id == seed.pk:
                continue
            similarity, similarity_reasons = _product_similarity(seed, candidate)
            if similarity <= 0:
                continue
            scores[candidate_id] += seed_weight * similarity
            reasons[candidate_id][signal_name] += 1
            for reason in similarity_reasons:
                reasons[candidate_id][reason] += 1

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
            tuple(reason for reason, _ in reasons[pk].most_common(3)),
        )
        for pk in ranked_ids[:limit]
    ]

    if len(ranked) < limit:
        existing_ids = purchased_ids | {r.product.pk for r in ranked}
        ranked.extend(popular_products(limit - len(ranked), exclude_ids=existing_ids))

    return ranked[:limit]


def recommend(*, user=None, product: Product | None = None, limit: int = 8) -> list[Recommendation]:
    limit = max(1, min(int(limit or 8), 24))
    if product is not None:
        return similar_products(product, limit)
    return recommendations_for_user(user, limit)
