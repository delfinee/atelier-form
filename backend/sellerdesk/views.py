from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from accounts.permissions import IsSeller
from products.models import Maker
from concierge import services as commerce
from concierge.models import Conversation
from concierge.serializers import ChatInput, DraftInput, ActionInput
from . import services
from .models import CustomerSession, SellerReply


class DeskThrottle(UserRateThrottle):
    rate = "120/min"
    scope = "seller_workbench"


class SellerAPI(APIView):
    permission_classes = [IsSeller]
    throttle_classes = [DeskThrottle]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        commerce.require_demo()
        if not Maker.objects.filter(owner=request.user, is_active=True).exists():
            raise PermissionDenied

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


@login_required
@ensure_csrf_cookie
def desk(request):
    commerce.require_demo()
    if not IsSeller().has_permission(request, None) or not request.user.maker_profile.is_active:
        raise PermissionDenied
    return render(request, "sellerdesk/desk.html", {"maker": request.user.maker_profile,
        "public_demo": settings.PUBLIC_CONCIERGE_DEMO, "csrf_cookie_name": settings.CSRF_COOKIE_NAME})


class Overview(SellerAPI):
    def get(self, request):
        conversations = Conversation.objects.filter(maker=request.user.maker_profile).prefetch_related(
            "messages", "seller_replies").select_related("customer_access").order_by("-updated_at")
        result = []
        for c in conversations[:100]:
            incoming = list(c.messages.all())
            replies = list(c.seller_replies.all())
            latest = incoming[-1] if incoming else None
            waiting = bool(latest and (not replies or replies[-1].created_at < latest.created_at))
            result.append({"id": str(c.uuid), "label": c.customer_label,
                "channel": "Mini Program preview" if hasattr(c, "customer_access") else "Web assistant",
                "preview": latest.text[:100] if latest else "Waiting for the customer's first message",
                "needs_reply": waiting, "at": c.updated_at.isoformat()})
        records = [services.draft_data(d) for d in services.seller_drafts(request.user)]
        counts = {s: sum(d["stage"] == s for d in records) for s in
                  ("review", "payment", "packing", "dispatch", "shipped", "expired", "attention")}
        return Response({"conversations": result, "conversation_total": conversations.count(),
            "drafts": records[:200], "draft_total": len(records), "counts": counts,
            "catalog": commerce.catalogue(request.user.maker_profile), "currency": settings.CURRENCY,
            "needs_reply": sum(c["needs_reply"] for c in result),
            "connection": {"state": "not_connected", "label": "WeChat not connected",
                "mode": "preview", "api_version": "v1"}})


class InvitationInput(serializers.Serializer):
    label = serializers.CharField(max_length=80, default="Alex · Demo customer")


class Invitations(SellerAPI):
    def post(self, request):
        data = InvitationInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(services.invite(request.user, data.validated_data["label"]), status=201)


class Detail(SellerAPI):
    def get(self, request, uuid):
        return Response(services.conversation_data(commerce.scoped_conversation(request.user, uuid)))


class Reply(SellerAPI):
    def post(self, request, uuid):
        data = ChatInput(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            c = commerce.scoped_conversation(request.user, uuid, lock=True)
            SellerReply.objects.get_or_create(conversation=c, request_id=data.validated_data["request_id"],
                defaults={"actor": request.user, "text": data.validated_data["text"]})
            c.save(update_fields=["updated_at"])
        return Response(services.conversation_data(c))


class Quote(SellerAPI):
    def post(self, request, uuid):
        data = DraftInput(data=request.data)
        data.is_valid(raise_exception=True)
        draft = commerce.make_draft(request.user, uuid, data.validated_data)
        return Response(services.draft_data(draft))


class Action(SellerAPI):
    def post(self, request, uuid):
        data = ActionInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(services.draft_data(commerce.act(request.user, uuid, data.validated_data)))


class Revoke(SellerAPI):
    def post(self, request, uuid):
        c = commerce.scoped_conversation(request.user, uuid)
        CustomerSession.objects.filter(conversation=c).update(revoked=True)
        return Response({"revoked": True})
