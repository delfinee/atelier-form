"""Editorial endpoints plus the two inbound forms."""

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminUserRole

from .models import FAQ, Article, ContactMessage, FAQGroup, NewsletterSubscriber
from .serializers import (
    ArticleDetailSerializer, ArticleListSerializer, ContactMessageSerializer,
    FAQGroupSerializer, FAQSerializer, NewsletterSerializer,
)


class ArticleViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = "slug"
    queryset = Article.objects.published()

    def get_serializer_class(self):
        return ArticleDetailSerializer if self.action == "retrieve" else ArticleListSerializer


class FAQViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Flat list of questions. `/api/faqs/groups/` returns them grouped."""

    serializer_class = FAQSerializer
    queryset = FAQ.objects.filter(is_active=True).select_related("group")
    filterset_fields = ["group__slug"]


class FAQGroupViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = FAQGroupSerializer
    queryset = FAQGroup.objects.filter(is_active=True).prefetch_related("faqs")


class NewsletterSubscribeView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "newsletter"
    serializer_class = NewsletterSerializer

    @extend_schema(summary="Subscribe to the newsletter", request=NewsletterSerializer,
                   responses={200: None, 201: None},
                   description="Subscribing twice is not an error -- a dormant record is reactivated.")
    def post(self, request):
        serializer = NewsletterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower().strip()

        subscriber = NewsletterSubscriber.objects.filter(email=email).first()
        if subscriber:
            if not subscriber.is_active:
                subscriber.resubscribe()
            # Same response either way: this endpoint must not disclose whether
            # an address is already on the list.
            return Response({"detail": "You're on the list. Look out for the next note."},
                            status=status.HTTP_200_OK)

        NewsletterSubscriber.objects.create(email=email)
        return Response({"detail": "You're on the list. Look out for the next note."},
                        status=status.HTTP_201_CREATED)


class ContactView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "contact"
    serializer_class = ContactMessageSerializer

    @extend_schema(summary="Send the studio a message", request=ContactMessageSerializer,
                   responses={201: ContactMessageSerializer})
    def post(self, request):
        serializer = ContactMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# -- admin ----------------------------------------------------------------

class AdminArticleViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUserRole]
    serializer_class = ArticleDetailSerializer
    queryset = Article.objects.all()
    lookup_field = "slug"


class AdminFAQViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUserRole]
    serializer_class = FAQSerializer
    queryset = FAQ.objects.all().select_related("group")


class AdminContactViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAdminUserRole]
    serializer_class = ContactMessageSerializer
    queryset = ContactMessage.objects.all()
    lookup_field = "uuid"
    filterset_fields = ["status"]
