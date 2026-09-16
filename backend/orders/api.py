"""Cart, checkout and order endpoints."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Address
from accounts.permissions import IsAdminUserRole, IsSeller
from payments.services import get_payment_provider
from products.models import Product, ProductVariant

from . import services
from .models import Order
from .serializers import (
    AddToCartSerializer, AdminOrderUpdateSerializer, CartSerializer,
    CheckoutSerializer, OrderSerializer, SellerFulfillmentUpdateSerializer,
    SellerOrderSerializer, UpdateCartItemSerializer,
)


class CartView(APIView):
    """The caller's bag. Works signed in (bound to the user) or out (session)."""

    permission_classes = [AllowAny]
    serializer_class = CartSerializer

    @extend_schema(summary="Read the current cart", responses=CartSerializer)
    def get(self, request):
        cart = services.get_cart(request)
        return Response(CartSerializer(cart).data)

    @extend_schema(summary="Empty the cart", responses={204: None})
    def delete(self, request):
        cart = services.get_cart(request, create=False)
        if cart:
            services.clear(cart)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartItemsView(APIView):
    permission_classes = [AllowAny]
    serializer_class = AddToCartSerializer

    @extend_schema(summary="Add a line to the cart", request=AddToCartSerializer,
                   responses={201: CartSerializer})
    def post(self, request):
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = services.get_cart(request)
        try:
            services.add_item(
                cart,
                product_slug=serializer.validated_data["product_slug"],
                variant_id=serializer.validated_data.get("variant") or None,
                quantity=serializer.validated_data["quantity"],
            )
        except Product.DoesNotExist:
            return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)
        except ProductVariant.DoesNotExist as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(CartSerializer(cart).data, status=status.HTTP_201_CREATED)


class CartItemDetailView(APIView):
    permission_classes = [AllowAny]
    serializer_class = UpdateCartItemSerializer

    @extend_schema(summary="Change a line's quantity (0 removes it)",
                   request=UpdateCartItemSerializer, responses=CartSerializer)
    def patch(self, request, item_id):
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = services.get_cart(request)
        try:
            services.set_quantity(cart, item_id, serializer.validated_data["quantity"])
        except Exception as exc:
            from .models import CartItem
            if isinstance(exc, CartItem.DoesNotExist):
                return Response({"detail": "That line is not in your bag."},
                                status=status.HTTP_404_NOT_FOUND)
            raise
        return Response(CartSerializer(cart).data)

    @extend_schema(summary="Remove a line", responses=CartSerializer)
    def delete(self, request, item_id):
        cart = services.get_cart(request)
        if not services.remove_item(cart, item_id):
            return Response({"detail": "That line is not in your bag."},
                            status=status.HTTP_404_NOT_FOUND)
        return Response(CartSerializer(cart).data)


class CheckoutView(APIView):
    """Create an order from the caller's cart.

    Totals are recalculated here from the database. Nothing about price, stock
    or payment outcome is taken from the request.
    """

    permission_classes = [AllowAny]
    serializer_class = CheckoutSerializer

    @extend_schema(summary="Place an order", request=CheckoutSerializer,
                   responses={201: OrderSerializer})
    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        cart = services.get_cart(request, create=False)
        if cart is None or not cart.items.exists():
            return Response({"detail": "Your bag is empty."}, status=status.HTTP_400_BAD_REQUEST)

        address_snapshot = self._resolve_address(request, data)
        if address_snapshot is None:
            return Response({"detail": "Delivery address not found."},
                            status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            order = services.create_order(
                cart=cart,
                user=request.user,
                email=data["email"],
                phone=data.get("phone", ""),
                shipping_address=address_snapshot,
                delivery_method=data["delivery_method"],
                gift_note=data.get("gift_note", ""),
            )
            # A payment session is opened, but the order is *not* marked paid.
            # Only the provider webhook can do that.
            session = get_payment_provider().create_session(order)

        payload = OrderSerializer(order).data
        payload["payment"] = {
            "provider": session.payment.provider,
            "session_id": session.session_id,
            "checkout_url": session.checkout_url,
            "state": session.payment.state,
        }
        return Response(payload, status=status.HTTP_201_CREATED)

    def _resolve_address(self, request, data) -> dict | None:
        if data.get("shipping_address_uuid"):
            if not request.user.is_authenticated:
                return None
            # Scoped to the caller: you cannot post someone else's address uuid.
            address = Address.objects.filter(user=request.user,
                                             uuid=data["shipping_address_uuid"]).first()
            return address.snapshot() if address else None

        supplied = dict(data["shipping_address"])
        if data.get("save_address") and request.user.is_authenticated:
            Address.objects.create(user=request.user, **supplied)
        return supplied


@extend_schema_view(
    list=extend_schema(summary="Your orders"),
    retrieve=extend_schema(summary="One of your orders"),
)
class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer
    lookup_field = "uuid"
    # Declared so the schema generator can infer the model without a request.
    queryset = Order.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        # Scoped to the caller. An order uuid belonging to someone else 404s.
        return Order.objects.filter(user=self.request.user).prefetch_related("items")


class SellerOrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
    """Orders containing this seller's lines, without exposing other sellers' items."""

    permission_classes = [IsSeller]
    serializer_class = SellerOrderSerializer
    lookup_field = "uuid"
    queryset = Order.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return Order.objects.none()
        return (Order.objects.filter(items__maker__owner=self.request.user)
                .distinct().prefetch_related("items", "items__maker", "seller_fulfillments"))

    @extend_schema(
        summary="Update your fulfilment status and tracking for this order",
        request=SellerFulfillmentUpdateSerializer,
        responses=SellerOrderSerializer,
    )
    @action(detail=True, methods=["patch"], url_path="fulfilment")
    def fulfilment(self, request, uuid=None):
        """Allow the seller to update their own carrier, tracking number and status.

        Only the SellerFulfillment that belongs to this seller can be changed.
        Samuel's service function enforces ownership and syncs the parent order.
        """
        order = self.get_object()  # 404s if seller has no items in this order
        maker = request.user.maker_profile
        fulfillment = get_object_or_404(order.seller_fulfillments, maker=maker)

        serializer = SellerFulfillmentUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        services.update_seller_fulfillment(
            fulfillment,
            acting_maker=maker,
            status=serializer.validated_data.get("status"),
            carrier=serializer.validated_data.get("carrier"),
            tracking_number=serializer.validated_data.get("tracking_number"),
        )
        # Refresh the order so the serializer sees the updated fulfillment values.
        order.refresh_from_db()
        return Response(SellerOrderSerializer(order, context={"request": request}).data)


class AdminOrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Order oversight. Requires is_admin."""

    permission_classes = [IsAdminUserRole]
    lookup_field = "uuid"
    queryset = Order.objects.all().prefetch_related("items").select_related("user")
    filterset_fields = ["status", "payment_status", "fulfillment_status"]

    def get_serializer_class(self):
        return AdminOrderUpdateSerializer if self.action in {"update", "partial_update"} else OrderSerializer
