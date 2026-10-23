from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle, SimpleRateThrottle
from accounts.permissions import IsSeller
from . import assistant, services
from .models import Conversation, Message
from .serializers import ChatInput, DraftInput, ActionInput


class ChatThrottle(UserRateThrottle):
    rate = "15/min"
    scope = "concierge"


class PublicChatBudgetThrottle(SimpleRateThrottle):
    rate = "120/hour"
    scope = "public_concierge_budget"

    def get_cache_key(self, request, view):
        return "public_concierge_chat_budget" if settings.PUBLIC_CONCIERGE_DEMO else None


@login_required
@ensure_csrf_cookie
def desk(request):
    if not IsSeller().has_permission(request, None):
        raise PermissionDenied
    services.require_demo()
    template = "concierge/desk_en.html" if settings.PUBLIC_CONCIERGE_DEMO else "concierge/desk.html"
    return render(request, template, {"maker": request.user.maker_profile,
        "ai_configured": bool(settings.DEEPSEEK_API_KEY),
        "public_demo": settings.PUBLIC_CONCIERGE_DEMO})


@api_view(["GET", "POST"])
@permission_classes([IsSeller])
def conversations(request):
    services.require_demo()
    maker = request.user.maker_profile
    if not maker.is_active:
        raise PermissionDenied
    if request.method == "POST":
        conversation = Conversation.objects.create(maker=maker, created_by=request.user,
            customer_label="Demo customer" if settings.PUBLIC_CONCIERGE_DEMO else "模拟微信客户")
        return Response({"id": str(conversation.uuid)}, status=201)
    return Response({"catalog": services.catalogue(maker),
        "conversations": [{"id": str(c.uuid), "label": c.customer_label,
                           "at": c.created_at.isoformat()} for c in
                          Conversation.objects.filter(maker=maker).order_by("-id")[:30]]})


@api_view(["GET"])
@permission_classes([IsSeller])
def conversation_detail(request, uuid):
    services.require_demo()
    c = services.scoped_conversation(request.user, uuid)
    return Response({"messages": [{"text": m.text, **m.response} for m in c.messages.all()],
                     "drafts": [services.draft_data(d) for d in c.drafts.order_by("id")]})


@api_view(["POST"])
@permission_classes([IsSeller])
@throttle_classes([ChatThrottle, PublicChatBudgetThrottle])
def message(request, uuid):
    services.require_demo()
    data = ChatInput(data=request.data)
    data.is_valid(raise_exception=True)
    c = services.scoped_conversation(request.user, uuid)
    previous = c.messages.filter(request_id=data.validated_data["request_id"]).first()
    if previous:
        return Response(previous.response)
    history = list(c.messages.order_by("-id")[:6])[::-1]
    reply = assistant.suggest(data.validated_data["text"], services.catalogue(c.maker), history)
    # Keep slow network requests outside DB transactions. Racing retries may
    # make two model calls, but the unique key stores only one visible message.
    with transaction.atomic():
        services.scoped_conversation(request.user, uuid, lock=True)
        saved, _ = Message.objects.get_or_create(conversation=c, request_id=data.validated_data["request_id"],
            defaults={"text": data.validated_data["text"], "response": reply})
    return Response(saved.response)


@api_view(["POST"])
@permission_classes([IsSeller])
def draft(request, uuid):
    data = DraftInput(data=request.data)
    data.is_valid(raise_exception=True)
    return Response(services.draft_data(services.make_draft(request.user, uuid, data.validated_data)))


@api_view(["POST"])
@permission_classes([IsSeller])
def action(request, uuid):
    data = ActionInput(data=request.data)
    data.is_valid(raise_exception=True)
    return Response(services.draft_data(services.act(request.user, uuid, data.validated_data)))
