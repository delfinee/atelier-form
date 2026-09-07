"""Query-parameter filtering for the product list endpoint."""

import django_filters as filters
from django.db.models import Q

from .models import MATERIAL_FAMILIES, MATERIAL_ALIASES, Product

SORT_MAP = {
    "featured": ["-is_featured", "-sort_weight", "-created_at"],
    "newest": ["-created_at"],
    "price_asc": ["price"],
    "price_desc": ["-price"],
    # Accept the frontend's hyphenated spellings too.
    "price-asc": ["price"],
    "price-desc": ["-price"],
}


class ProductFilter(filters.FilterSet):
    category = filters.CharFilter(field_name="category__slug", lookup_expr="iexact")
    collection = filters.CharFilter(field_name="collections__slug", lookup_expr="iexact")
    maker = filters.CharFilter(field_name="maker__slug", lookup_expr="iexact")
    min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    featured = filters.BooleanFilter(field_name="is_featured")
    new_arrival = filters.BooleanFilter(field_name="is_new_arrival")
    availability = filters.CharFilter(method="filter_availability")
    material = filters.CharFilter(method="filter_material")
    colour = filters.CharFilter(method="filter_colour")
    search = filters.CharFilter(method="filter_search")
    sort = filters.CharFilter(method="apply_sort")

    class Meta:
        model = Product
        fields = ["category", "collection", "maker", "featured", "new_arrival"]

    def filter_availability(self, queryset, name, value):
        values = [v for v in value.split(",") if v]
        return queryset.filter(stock_status__in=values) if values else queryset

    def filter_material(self, queryset, name, value):
        """Match the curated material families the shop facets on.

        Families are keyword sets rather than stored values ("Wood" also means
        oak and timber), so this matches their aliases against the search blob.
        """
        families = [f for f in value.split(",") if f in MATERIAL_FAMILIES]
        if not families:
            return queryset
        clause = Q()
        for family in families:
            for alias in MATERIAL_ALIASES[family]:
                clause |= Q(search_blob__icontains=alias)
        return queryset.filter(clause).distinct()

    def filter_colour(self, queryset, name, value):
        labels = [v for v in value.split(",") if v]
        if not labels:
            return queryset
        return queryset.filter(product_variants__group="colour",
                               product_variants__label__in=labels).distinct()

    def filter_search(self, queryset, name, value):
        return queryset.search(value)

    def apply_sort(self, queryset, name, value):
        return queryset.order_by(*SORT_MAP.get(value, SORT_MAP["featured"]))
