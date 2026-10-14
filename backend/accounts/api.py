"""Authentication, profile, addresses and wishlist endpoints."""

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils.translation import gettext
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from content.services import send_welcome
from products.models import Product

from .models import Address, WishlistItem
from .permissions import IsOwner
from .serializers import (
    AddressSerializer, ChangePasswordSerializer, LoginSerializer,
    RegisterSerializer, UserSerializer, WishlistItemSerializer,
)

User = get_user_model()


def _tokens_for(user) -> dict:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"
    serializer_class = RegisterSerializer

    @extend_schema(summary="Create an account", request=RegisterSerializer,
                   responses={201: UserSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        send_welcome(user)                       # never blocks registration
        return Response(
            {"user": UserSerializer(user).data, "tokens": _tokens_for(user)},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"
    serializer_class = LoginSerializer

    @extend_schema(summary="Sign in and receive a JWT pair", request=LoginSerializer,
                   responses={200: UserSerializer})
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        # Anything already in an anonymous bag follows the customer in.
        from orders.services import merge_session_cart
        if request.session.session_key:
            merge_session_cart(request, user)

        return Response({"user": UserSerializer(user).data, "tokens": _tokens_for(user)})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Sign out",
                   description=("Stateless JWTs cannot be revoked without a blacklist, so the "
                                "client discards its tokens. Any Django session is flushed here."),
                   request=None, responses={204: None})
    def post(self, request):
        if request.session.session_key:
            request.session.flush()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    @extend_schema(summary="The signed-in user", responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    @extend_schema(summary="Update your profile", request=UserSerializer, responses=UserSerializer)
    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"
    serializer_class = ChangePasswordSerializer

    @extend_schema(summary="Change your password", request=ChangePasswordSerializer,
                   responses={200: None})
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": gettext("Password updated.")})


@extend_schema_view(
    list=extend_schema(summary="Your saved addresses"),
    create=extend_schema(summary="Save an address"),
)
class AddressViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOwner]
    serializer_class = AddressSerializer
    lookup_field = "uuid"
    queryset = Address.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Address.objects.none()
        # Scoped to the caller, so one user can never read another's addresses.
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class WishlistViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WishlistItemSerializer
    queryset = WishlistItem.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return WishlistItem.objects.none()
        return (WishlistItem.objects.filter(user=self.request.user)
                .select_related("product", "product__category", "product__maker")
                .prefetch_related("product__product_images"))


@extend_schema(summary="Add a product to your wishlist", request=None,
               responses={201: WishlistItemSerializer, 200: WishlistItemSerializer})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def wishlist_add(request, slug):
    product = Product.objects.active().filter(slug=slug).first()
    if product is None:
        return Response({"detail": gettext("Product not found.")}, status=status.HTTP_404_NOT_FOUND)
    try:
        item, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
    except IntegrityError:
        # Lost a race against a concurrent add; the row exists either way.
        item, created = WishlistItem.objects.get(user=request.user, product=product), False
    return Response(WishlistItemSerializer(item).data,
                    status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@extend_schema(summary="Remove a product from your wishlist", responses={204: None})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def wishlist_remove(request, slug):
    deleted, _ = WishlistItem.objects.filter(user=request.user, product__slug=slug).delete()
    if not deleted:
        return Response({"detail": gettext("That product is not in your wishlist.")},
                        status=status.HTTP_404_NOT_FOUND)
    return Response(status=status.HTTP_204_NO_CONTENT)
