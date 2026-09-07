"""Catalogue endpoints. All read-only and public, except the admin viewsets."""

from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from accounts.permissions import IsAdminUserRole, IsSeller

from .filters import SORT_MAP, ProductFilter
from .models import Category, Collection, Maker, Product, ProductVariant
from .serializers import (
    AdminProductSerializer, AdminStockSerializer, CategorySerializer, CollectionSerializer,
    MakerDetailSerializer, MakerListSerializer, ProductDetailSerializer, ProductListSerializer,
    SellerProductSerializer,
)


@extend_schema_view(
    list=extend_schema(summary="List products", description=(
        "Filter with category, collection, maker, material, colour, availability, "
        "min_price, max_price, featured, new_arrival and search. Sort with "
        "featured | newest | price_asc | price_desc. Paginate with page and limit."
    )),
    retrieve=extend_schema(summary="Retrieve one product by slug"),
)
class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = "slug"
    filterset_class = ProductFilter
    serializer_class = ProductListSerializer

    def get_queryset(self):
        queryset = Product.objects.active().with_related()
        # django-filter applies `sort` itself; this is the default ordering.
        if "sort" not in self.request.query_params:
            queryset = queryset.order_by(*SORT_MAP["featured"])
        return queryset

    def get_serializer_class(self):
        return ProductDetailSerializer if self.action == "retrieve" else ProductListSerializer

    @extend_schema(summary="Facet counts for the shop filter rail")
    @action(detail=False, methods=["get"])
    def facets(self, request):
        products = Product.objects.active()
        colours = (ProductVariant.objects.filter(group="colour", is_active=True,
                                                 product__is_active=True)
                   .values("label", "swatch").distinct().order_by("label"))
        return Response({
            "categories": [
                {"value": c.slug, "label": c.name, "count": c.product_count}
                for c in Category.objects.filter(is_active=True).annotate(
                    product_count=Count("products", filter=Q(products__is_active=True)))
            ],
            "colours": [{"value": c["label"], "label": c["label"], "swatch": c["swatch"]}
                        for c in colours],
            "availability": [{"value": v, "label": lbl} for v, lbl in
                             [("in-stock", "In stock"), ("low-stock", "Low stock"),
                              ("made-to-order", "Made to order")]],
            "price_max": products.order_by("-price").values_list("price", flat=True).first() or 0,
        })


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = "slug"
    serializer_class = CategorySerializer
    # `.annotate()` adds a GROUP BY that drops the model's Meta ordering, which
    # makes paginated results non-deterministic -- so order explicitly.
    queryset = Category.objects.filter(is_active=True).annotate(
        product_count=Count("products", filter=Q(products__is_active=True))
    ).order_by("sort_order", "name")

    @extend_schema(summary="Products in a category", responses=ProductListSerializer(many=True))
    @action(detail=True, methods=["get"])
    def products(self, request, slug=None):
        return _paginated_products(self, Product.objects.active().with_related()
                                   .filter(category__slug=slug))


class CollectionViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = "slug"
    serializer_class = CollectionSerializer
    queryset = Collection.objects.filter(is_active=True).annotate(
        product_count=Count("products", filter=Q(products__is_active=True))
    ).order_by("sort_order", "name")

    @extend_schema(summary="Products in a collection", responses=ProductListSerializer(many=True))
    @action(detail=True, methods=["get"])
    def products(self, request, slug=None):
        return _paginated_products(self, Product.objects.active().with_related()
                                   .filter(collections__slug=slug))


class MakerViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = "slug"
    queryset = Maker.objects.filter(is_active=True)

    def get_serializer_class(self):
        return MakerDetailSerializer if self.action == "retrieve" else MakerListSerializer

    @extend_schema(summary="Products by a maker", responses=ProductListSerializer(many=True))
    @action(detail=True, methods=["get"])
    def products(self, request, slug=None):
        return _paginated_products(self, Product.objects.active().with_related()
                                   .filter(maker__slug=slug))


def _paginated_products(view, queryset):
    """Shared body for the three `/{slug}/products/` sub-resources."""
    page = view.paginate_queryset(queryset)
    serializer = ProductListSerializer(page, many=True, context=view.get_serializer_context())
    return view.get_paginated_response(serializer.data)


# -- admin ----------------------------------------------------------------

class SellerProductViewSet(viewsets.ModelViewSet):
    """Self-service catalogue management scoped to the signed-in maker."""

    permission_classes = [IsSeller]
    serializer_class = SellerProductSerializer
    lookup_field = "slug"
    queryset = Product.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return Product.objects.none()
        return Product.objects.filter(maker__owner=self.request.user).select_related(
            "category", "maker",
        ).prefetch_related("collections")

    def perform_create(self, serializer):
        serializer.save(maker=self.request.user.maker_profile)


# -- admin ----------------------------------------------------------------

class AdminProductViewSet(viewsets.ModelViewSet):
    """Full product CRUD plus a stock adjustment action. Requires is_admin."""

    permission_classes = [IsAdminUserRole]
    serializer_class = AdminProductSerializer
    queryset = Product.objects.all().select_related("category", "maker")
    lookup_field = "slug"

    @extend_schema(summary="Set stock for a product or one of its variants",
                   request=AdminStockSerializer, responses=AdminProductSerializer)
    @action(detail=True, methods=["post"])
    def stock(self, request, slug=None):
        product = self.get_object()
        serializer = AdminStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data["stock_quantity"]
        variant_uuid = serializer.validated_data.get("variant_uuid")

        if variant_uuid:
            variant = product.product_variants.filter(uuid=variant_uuid).first()
            if variant is None:
                raise NotFound("No such variant on this product.")
            variant.stock_quantity = quantity
            variant.save(update_fields=["stock_quantity", "updated_at"])
        else:
            product.stock_quantity = quantity
            product.save(update_fields=["stock_quantity", "updated_at"])

        product.refresh_from_db()
        product.refresh_stock_status()
        product.refresh_from_db()
        return Response(AdminProductSerializer(product).data, status=status.HTTP_200_OK)


class AdminCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUserRole]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    lookup_field = "slug"


class AdminCollectionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUserRole]
    serializer_class = CollectionSerializer
    queryset = Collection.objects.all()
    lookup_field = "slug"


class AdminMakerViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUserRole]
    serializer_class = MakerDetailSerializer
    queryset = Maker.objects.all()
    lookup_field = "slug"
