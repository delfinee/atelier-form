"""Data access for the frontend.

This module is the seam between the presentation layer and the database. It was
written against `frontend.mockdata` while the frontend was built; it now reads
through the ORM. Views and templates were not rewritten -- they call the same
functions and get the same shapes, because the models carry compatibility
properties (`Product.images`, `Product.variants`, `Collection.title`) that match
what the templates were built against.

`frontend.mockdata` survives as the seed fixture and as the home of static
site copy, and no longer serves a single request.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, cast

from django.db.models import Case, IntegerField, Q, When

from content.models import Article, ArticleQuerySet
from products.models import (
    MATERIAL_ALIASES, MATERIAL_FAMILIES, Category, Collection, Maker, Product,
    ProductQuerySet, ProductVariant,
)

SORT_OPTIONS = [
    ("featured", "Featured"),
    ("newest", "Newest"),
    ("price-asc", "Price: Low to High"),
    ("price-desc", "Price: High to Low"),
]

AVAILABILITY_OPTIONS = [
    ("in-stock", "In stock"),
    ("low-stock", "Low stock"),
    ("made-to-order", "Made to order"),
]

PRICE_BANDS = [
    ("under-40", "Under ¥40", 0, 40),
    ("40-70", "¥40 – ¥70", 40, 70),
    ("70-100", "¥70 – ¥100", 70, 100),
    ("over-100", "Over ¥100", 100, 10_000),
]

POPULAR_SEARCHES = ["Stoneware mug", "Indigo", "Candle", "Linen", "Gifts under ¥50"]

_SORT_FIELDS = {
    "newest": ["-sort_weight", "-created_at"],
    "price-asc": ["price"],
    "price-desc": ["-price"],
    "featured": ["-is_featured", "-sort_weight", "-created_at"],
}


def _base_queryset():
    manager = cast(ProductQuerySet, Product.objects)
    return manager.active().with_related()


# -- Products ------------------------------------------------------------

def all_products() -> list[Product]:
    return list(_base_queryset())


def get_product(slug: str) -> Product | None:
    return _base_queryset().filter(slug=slug).first()


def featured_products(limit: int | None = None) -> list[Product]:
    queryset = _base_queryset().filter(is_featured=True)
    return list(queryset[:limit] if limit else queryset)


def new_arrivals(limit: int = 8) -> list[Product]:
    return list(_base_queryset().filter(is_new_arrival=True)
                .order_by("-sort_weight", "-created_at")[:limit])


def products_by_maker(maker_slug: str) -> list[Product]:
    return list(_base_queryset().filter(maker__slug=maker_slug))


def related_products(product: Product, limit: int = 4) -> list[Product]:
    """Same maker first, then same category, then nearest in price.

    Ranked in SQL so the whole catalogue is not pulled into memory as it grows.
    """
    return list(
        _base_queryset()
        .exclude(pk=product.pk)
        .annotate(
            same_maker=Case(When(maker=product.maker, then=0), default=1,
                            output_field=IntegerField()),
            same_category=Case(When(category=product.category, then=0), default=1,
                               output_field=IntegerField()),
        )
        .order_by("same_maker", "same_category", "-is_featured", "-sort_weight")[:limit]
    )


def filter_products(
    *,
    categories: Iterable[str] = (),
    materials: Iterable[str] = (),
    colours: Iterable[str] = (),
    price_bands: Iterable[str] = (),
    availability: Iterable[str] = (),
    collection: str | None = None,
    sort: str = "featured",
) -> list[Product]:
    """Faceted shop filtering, entirely in SQL."""
    queryset = _base_queryset()

    if collection:
        # A slug may name either an editorial collection or a category.
        queryset = queryset.filter(Q(collections__slug=collection) | Q(category__slug=collection))

    categories = [c for c in categories if c]
    if categories:
        queryset = queryset.filter(category__slug__in=categories)

    materials = [m for m in materials if m in MATERIAL_FAMILIES]
    if materials:
        clause = Q()
        for family in materials:
            for alias in MATERIAL_ALIASES[family]:
                clause |= Q(search_blob__icontains=alias)
        queryset = queryset.filter(clause)

    colours = [c for c in colours if c]
    if colours:
        queryset = queryset.filter(product_variants__group="colour",
                                   product_variants__label__in=colours)

    availability = [a for a in availability if a]
    if availability:
        queryset = queryset.filter(stock_status__in=availability)

    bands = [b for b in PRICE_BANDS if b[0] in set(price_bands)]
    if bands:
        clause = Q()
        for _, _, low, high in bands:
            clause |= Q(price__gte=Decimal(low), price__lte=Decimal(high))
        queryset = queryset.filter(clause)

    return list(queryset.distinct().order_by(*_SORT_FIELDS.get(sort, _SORT_FIELDS["featured"])))


def sort_products(items: list[Product], sort: str) -> list[Product]:
    """In-memory sort, for lists that have already been fetched."""
    if sort == "newest":
        return sorted(items, key=lambda p: (p.sort_weight, p.created_at), reverse=True)
    if sort == "price-asc":
        return sorted(items, key=lambda p: p.price)
    if sort == "price-desc":
        return sorted(items, key=lambda p: p.price, reverse=True)
    return sorted(items, key=lambda p: (not p.is_featured, -p.sort_weight))


def shop_facets() -> dict[str, Any]:
    """Everything the filter rail needs, counted in the database."""
    from django.db.models import Count

    category_rows = (Category.objects.filter(is_active=True)
                     .annotate(count=Count("products", filter=Q(products__is_active=True)))
                     .order_by("sort_order", "name"))

    # Material families are keyword sets, not stored values, so their counts
    # are one aggregate query per family rather than a GROUP BY.
    material_rows = []
    for family in MATERIAL_FAMILIES:
        clause = Q()
        for alias in MATERIAL_ALIASES[family]:
            clause |= Q(search_blob__icontains=alias)
        count = _base_queryset().filter(clause).count()
        if count:
            material_rows.append({"value": family, "label": family, "count": count})

    colour_rows = (ProductVariant.objects
                   .filter(group="colour", is_active=True, product__is_active=True)
                   .values("label", "swatch").distinct().order_by("label"))

    price_max = _base_queryset().order_by("-price").values_list("price", flat=True).first()

    return {
        "categories": [{"value": c.slug, "label": c.name, "count": getattr(c, "count", 0)}
                   for c in category_rows],
        "materials": material_rows,
        "colours": [{"value": r["label"], "label": r["label"], "swatch": r["swatch"]}
                    for r in colour_rows],
        "price_bands": [{"value": v, "label": lbl} for v, lbl, _, _ in PRICE_BANDS],
        "availability": [{"value": v, "label": lbl} for v, lbl in AVAILABILITY_OPTIONS],
        "price_max": price_max or 0,
    }


# -- Collections ---------------------------------------------------------

def all_collections() -> list:
    """Categories and editorial collections together, as the index page shows."""
    return list(Category.objects.filter(is_active=True)) + \
        list(Collection.objects.filter(is_active=True))


def categories() -> list[Category]:
    return list(Category.objects.filter(is_active=True))


def get_collection(slug: str):
    return (Collection.objects.filter(slug=slug, is_active=True).first()
            or Category.objects.filter(slug=slug, is_active=True).first())


def products_in_collection(slug: str, sort: str = "featured") -> list[Product]:
    return filter_products(collection=slug, sort=sort)


# -- Makers --------------------------------------------------------------

def all_makers() -> list[Maker]:
    return list(Maker.objects.filter(is_active=True))


def get_maker(slug: str) -> Maker | None:
    return Maker.objects.filter(slug=slug, is_active=True).first()


# -- Journal -------------------------------------------------------------

def all_articles() -> list[Article]:
    manager = cast(ArticleQuerySet, Article.objects)
    return list(manager.published())


def get_article(slug: str) -> Article | None:
    manager = cast(ArticleQuerySet, Article.objects)
    return manager.published().filter(slug=slug).first()


def related_articles(article: Article, limit: int = 2) -> list[Article]:
    manager = cast(ArticleQuerySet, Article.objects)
    return list(manager.published().exclude(pk=article.pk)[:limit])


# -- Search --------------------------------------------------------------

def search(query: str) -> dict[str, list]:
    """Substring search across every content type.

    ILIKE rather than PostgreSQL full-text search: the default text search
    configuration does not segment Simplified Chinese, so `搜索陶瓷杯` would not
    match once the catalogue is localised (charter review §4.5). The upgrade
    path is a pg_trgm GIN index, then zhparser/pg_jieba.
    """
    q = (query or "").strip()
    if not q:
        return {"products": [], "collections": [], "makers": [], "articles": []}

    collections = list(Collection.objects.filter(
        Q(name__icontains=q) | Q(tagline__icontains=q) | Q(description__icontains=q),
        is_active=True))
    collections += list(Category.objects.filter(
        Q(name__icontains=q) | Q(tagline__icontains=q) | Q(description__icontains=q),
        is_active=True))

    return {
        "products": list(_base_queryset().search(q)),
        "collections": collections,
        "makers": list(Maker.objects.filter(
            Q(name__icontains=q) | Q(discipline__icontains=q)
            | Q(location__icontains=q) | Q(tagline__icontains=q), is_active=True)),
        "articles": list(cast(ArticleQuerySet, Article.objects).published().filter(
            Q(title__icontains=q) | Q(standfirst__icontains=q) | Q(category__icontains=q))),
    }


# -- Catalogue payload for client-side state -----------------------------

def catalogue_payload() -> dict[str, dict]:
    """Slim product map consumed by the wishlist and recently-viewed JS.

    The browser stores slugs only, so prices and names cannot go stale or be
    tampered with -- they are read from here on every render.
    """
    from django.urls import reverse

    return {
        p.slug: {
            "slug": p.slug,
            "name": p.name,
            "price": float(p.price),
            "category": p.category.slug,
            "label": p.short_description,
            "image": p.product_images.all()[0].url if p.product_images.all() else "",
            "url": reverse("product_detail", args=[p.slug]),
            "stock": p.stock_status,
        }
        for p in _base_queryset()
    }
