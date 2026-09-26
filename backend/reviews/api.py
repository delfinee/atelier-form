"""Published reviews and verified-purchase review submission."""

from django.db import IntegrityError, transaction
from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.permissions import IsOwner
from orders.models import OrderItem, PaymentStatus

from .models import Review
from .serializers import ReviewSerializer
from .errors import is_duplicate_review_error


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    lookup_field = "uuid"
    queryset = Review.objects.none()
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [AllowAny()]
        if self.action == "create":
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsOwner()]

    def get_queryset(self):
        queryset = Review.objects.select_related("product", "user", "order_item")
        if self.action in {"update", "partial_update", "destroy"}:
            return queryset.filter(user=self.request.user)
        queryset = queryset.filter(is_published=True)
        product = self.request.query_params.get("product")
        return queryset.filter(product__slug=product) if product else queryset

    def perform_create(self, serializer):
        product = serializer.validated_data["product"]
        order_item = (OrderItem.objects.filter(
            order__user=self.request.user,
            order__payment_status=PaymentStatus.PAID,
            product=product,
        ).order_by("-order__placed_at").first())
        if order_item is None:
            raise PermissionDenied("Only verified buyers can review this product.")
        try:
            with transaction.atomic():
                serializer.save(user=self.request.user, order_item=order_item, is_published=True)
        except IntegrityError as exc:
            if not is_duplicate_review_error(exc):
                raise
            raise ValidationError({"detail": "You have already reviewed this product."}) from exc
