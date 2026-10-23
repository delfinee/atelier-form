"""Versioned customer API: no seller identity, packing or dispatch capability."""
from django.db import transaction
from django.shortcuts import get_object_or_404, render
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from concierge import assistant, services as commerce
from concierge.models import Message
from concierge.serializers import ChatInput
from concierge.views import PublicChatBudgetThrottle
from .auth import CustomerAuthentication
from . import services
from .models import CustomerAction


class CustomerThrottle(UserRateThrottle):
    rate = "120/min"
    scope = "store_customer"


class ChatThrottle(UserRateThrottle):
    rate = "15/min"
    scope = "store_customer_chat"


def preview(request):
    commerce.require_demo()
    response = render(request, "sellerdesk/customer.html")
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


class CustomerAPI(APIView):
    authentication_classes = [CustomerAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [CustomerThrottle]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        commerce.require_demo()

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class State(CustomerAPI):
    def get(self, request):
        c = request.auth.conversation
        return Response({**services.conversation_data(c), "demo": True,
            "store": c.maker.name, "expires_at": request.auth.expires_at.isoformat()})


class Catalog(CustomerAPI):
    def get(self, request):
        return Response({"items": commerce.catalogue(request.auth.conversation.maker)})


class Chat(CustomerAPI):
    throttle_classes = [ChatThrottle, PublicChatBudgetThrottle]

    def post(self, request):
        data = ChatInput(data=request.data)
        data.is_valid(raise_exception=True)
        c = request.auth.conversation
        previous = c.messages.filter(request_id=data.validated_data["request_id"]).first()
        if previous:
            return Response(previous.response)
        history = list(c.messages.order_by("-id")[:6])[::-1]
        reply = assistant.suggest(data.validated_data["text"], commerce.catalogue(c.maker), history)
        with transaction.atomic():
            commerce.scoped_conversation(c.maker.owner, c.uuid, lock=True)
            message, _ = Message.objects.get_or_create(conversation=c,
                request_id=data.validated_data["request_id"],
                defaults={"text": data.validated_data["text"], "response": reply})
            c.save(update_fields=["updated_at"])
        return Response(message.response)


class Confirm(CustomerAPI):
    @transaction.atomic
    def post(self, request, uuid):
        # Never take a conversation or maker from customer-supplied data.
        draft = get_object_or_404(request.auth.conversation.drafts.select_for_update(), uuid=uuid)
        if request.data.get("confirmed") is not True:
            return Response({"detail": "Please review and explicitly accept the quote."}, status=400)
        result = commerce.act(draft.conversation.maker.owner, uuid, {"action": "confirm", "confirmed": True})
        if not draft.order_id:
            CustomerAction.objects.get_or_create(session=request.auth, draft=draft, action="confirm")
        return Response(services.draft_data(result))


class DemoPayment(CustomerAPI):
    @transaction.atomic
    def post(self, request, uuid):
        draft = get_object_or_404(request.auth.conversation.drafts.select_for_update(), uuid=uuid)
        already_paid = draft.order_id and draft.order.payment_status == "paid"
        result = commerce.act(draft.conversation.maker.owner, uuid, {"action": "pay"})
        if not already_paid:
            CustomerAction.objects.get_or_create(session=request.auth, draft=draft, action="pay")
        return Response(services.draft_data(result))


class WechatLogin(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        # Reserved contract. The old /api/wechat/ demo creates seller identities
        # and MUST NOT be reused to authenticate customers into this API.
        return Response({"code": "wechat_not_connected", "detail":
            "WeChat login is not connected. Use a seller-issued preview invitation for this demo."}, status=503)
