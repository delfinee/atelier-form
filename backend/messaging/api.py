"""API endpoints for buyer-seller messaging."""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from products.models import Maker

from .models import Conversation, ConversationMessage
from .permissions import IsConversationParticipant
from .serializers import (
    ConversationMessageSerializer,
    ConversationSerializer,
    CreateConversationSerializer,
    SendMessageSerializer,
)
from . import services


class ConversationViewSet(viewsets.ModelViewSet):
    """Endpoints for managing buyer-seller conversations and message polling."""

    lookup_field = "uuid"
    permission_classes = [IsAuthenticated, IsConversationParticipant]
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return CreateConversationSerializer
        return ConversationSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Conversation.objects.none()

        role = self.request.query_params.get("role")
        if role == "seller":
            makers_qs = Maker.objects.filter(owner=user)
            if not makers_qs.exists() and hasattr(user, "maker_profile") and user.maker_profile:
                makers_qs = Maker.objects.filter(pk=user.maker_profile.pk)
            if not makers_qs.exists():
                raise PermissionDenied("A linked seller profile is required to view seller conversations.")
            return Conversation.objects.filter(
                maker__in=makers_qs
            ).select_related("buyer", "maker", "product", "order").prefetch_related("messages", "messages__sender").order_by("-updated_at")

        if role == "buyer":
            return Conversation.objects.filter(
                buyer=user
            ).select_related("buyer", "maker", "product", "order").prefetch_related("messages", "messages__sender").order_by("-updated_at")

        # By default (and for detail actions such as retrieve and messages action),
        # return any conversation where the user is either buyer or seller:
        return Conversation.objects.filter(
            models.Q(buyer=user) | models.Q(maker__owner=user)
        ).distinct().select_related(
            "buyer", "maker", "product", "order"
        ).prefetch_related("messages", "messages__sender").order_by("-updated_at")

    def create(self, request, *args, **kwargs):
        serializer = CreateConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        maker_ident = serializer.validated_data.get("maker")
        product_ident = serializer.validated_data.get("product")
        order_ident = serializer.validated_data.get("order")

        try:
            conversation, created = services.get_or_create_conversation(
                buyer=request.user,
                maker_identifier=maker_ident,
                product_identifier=product_ident,
                order_identifier=order_ident,
            )
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc))
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, "message") else str(exc)
            raise ValidationError({"detail": msg})

        out_serializer = ConversationSerializer(conversation, context={"request": request})
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(out_serializer.data, status=status_code)

    @action(detail=False, methods=["post"], url_path="translate")
    def translate(self, request):
        """Translate message between English and Chinese."""
        text = (request.data.get("text") or "").strip()
        target_lang = (request.data.get("target_lang") or request.data.get("target") or "").strip() or None
        result = services.translate_message(text, target_lang=target_lang)
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get", "post"], url_path="messages")
    def messages(self, request, uuid=None):
        conversation = self.get_object()

        if request.method == "GET":
            # Polling support via ?after=
            after_val = (request.query_params.get("after") or "").strip()
            messages_qs = conversation.messages.select_related("sender", "conversation", "conversation__maker")

            if after_val:
                cursor_msg = None
                try:
                    cursor_msg = conversation.messages.filter(uuid=after_val).first()
                except Exception:
                    pass

                if cursor_msg:
                    messages_qs = messages_qs.filter(id__gt=cursor_msg.id)
                else:
                    parsed_dt = parse_datetime(after_val)
                    if parsed_dt:
                        messages_qs = messages_qs.filter(created_at__gt=parsed_dt)

            # Mark incoming messages as read for this participant
            services.mark_messages_read(conversation, request.user)

            serializer = ConversationMessageSerializer(
                messages_qs.order_by("created_at"),
                many=True,
                context={"request": request},
            )
            return Response(serializer.data)

        # POST: Send new message
        send_serializer = SendMessageSerializer(data=request.data)
        send_serializer.is_valid(raise_exception=True)

        body = send_serializer.validated_data["body"]
        try:
            message = services.send_message(conversation, request.user, body)
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc))
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, "message") else str(exc)
            raise ValidationError({"detail": msg})

        out_serializer = ConversationMessageSerializer(message, context={"request": request})
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)
