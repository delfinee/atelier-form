from django.conf import settings
from django.http import Http404
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from products.models import Category
from . import services, planner, conversation, wechat
from .auth import WechatAuthentication, require_linked, channel
from .models import Conversation, WechatSession, WechatIdentity
from .serializers import MessageInput, ChangeInput, ConfirmInput


class UserThrottle(UserRateThrottle):
    scope = "seller_agent"
    rate = "60/min"


class LoginThrottle(AnonRateThrottle):
    scope = "seller_wechat_login"
    rate = "10/min"


class ChatThrottle(UserRateThrottle):
    scope = "seller_agent_chat"
    rate = "15/min"


class Base(APIView):
    authentication_classes = [WechatAuthentication, SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserThrottle]

    def initial(self, request, *args, **kwargs):
        if not settings.SELLER_AGENT_ENABLED:
            raise Http404
        super().initial(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response


class Linked(Base):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        require_linked(request)


class Public(Base):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]


class Status(Public):
    def get(self, request):
        return Response({"wechat_configured": bool(settings.WECHAT_SELLER_ENABLED and settings.WECHAT_APP_ID and settings.WECHAT_APP_SECRET),
            "developer_login": bool(settings.WECHAT_SELLER_ENABLED and wechat.local_developer_allowed(request)),
            "onboarding": conversation.ONBOARDING, "engine": "deepseek" if settings.SELLER_AGENT_USE_LLM and settings.SELLER_AGENT_API_KEY else "guided"})


class LoginInput(serializers.Serializer):
    code = serializers.CharField(max_length=256)


class Login(Public):
    def get_authenticate_header(self, request):
        return "SellerWechat"

    def post(self, request):
        if not settings.WECHAT_SELLER_ENABLED:
            raise wechat.Unavailable("The WeChat seller channel is disabled.")
        data = LoginInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(wechat.login(data.validated_data["code"]))


class DeveloperLogin(Public):
    def post(self, request):
        if not settings.WECHAT_SELLER_ENABLED:
            raise wechat.Unavailable("The WeChat seller channel is disabled.")
        return Response(wechat.developer_login(request), status=201)


class Me(Base):
    def get(self, request):
        linked = not isinstance(request.auth, WechatSession) or bool(request.auth.identity.user_id)
        return Response({"linked": linked, "is_seller": services.has_shop(request.user) if linked else False,
            "account": request.user.email if linked else None, "channel": channel(request),
            "onboarding": conversation.ONBOARDING})


class LinkStart(Base):
    def post(self, request):
        if not isinstance(request.auth, WechatSession):
            raise serializers.ValidationError("Start linking from your Mini Program session.")
        data = wechat.start_link(request.auth)
        data["url"] = request.build_absolute_uri("/seller/ai/link/") + "#token=" + data.pop("token")
        return Response(data)


class LinkInput(ConfirmInput):
    token = serializers.CharField(max_length=128)
    verification_code = serializers.RegexField(r"^[A-Za-z0-9]{6}$")


class WebOnly(Linked):
    authentication_classes = [SessionAuthentication, JWTAuthentication]


class LinkApprove(WebOnly):
    def post(self, request):
        data = LinkInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(wechat.approve_link(request.user, data.validated_data["token"], data.validated_data["verification_code"]))


class Links(WebOnly):
    def get(self, request):
        return Response({"links":[{"id":str(i.uuid), "mode":i.mode, "linked_at":i.updated_at.isoformat()}
            for i in WechatIdentity.objects.filter(user=request.user)]})


class Unlink(WebOnly):
    def post(self, request, uuid):
        data = ConfirmInput(data=request.data)
        data.is_valid(raise_exception=True)
        wechat.unlink(request.user, uuid)
        return Response({"unlinked":True})


class Logout(Base):
    def post(self, request):
        if not isinstance(request.auth, WechatSession):
            raise serializers.ValidationError("Use website logout for website sessions.")
        request.auth.delete()
        return Response(status=204)


class Conversations(Linked):
    def get(self, request):
        return Response({"conversations":[{"id":str(c.uuid), "at":c.updated_at.isoformat()}
            for c in Conversation.objects.filter(user=request.user).order_by("-id")[:30]]})

    def post(self, request):
        c = Conversation.objects.create(user=request.user)
        return Response({"id":str(c.uuid)}, status=201)


class Detail(Linked):
    def get(self, request, uuid):
        c = services.conversation_for(request.user, uuid)
        return Response({"id":str(c.uuid), "messages":[{"text":m.text,"response":m.response,"channel":m.channel}
            for m in c.messages.all()], "changes":[services.change_data(d) for d in c.changes.order_by("id")]})


class Chat(Linked):
    throttle_classes = [ChatThrottle]

    def post(self, request, uuid):
        data = MessageInput(data=request.data)
        data.is_valid(raise_exception=True)
        c = services.conversation_for(request.user, uuid)
        old = c.messages.filter(request_id=data.validated_data["request_id"]).first()
        if old:
            return Response(old.response)
        catalog = conversation.get_catalog(request.user)
        model_context = {}
        if planner.enabled():
            history = []
            for message in reversed(list(c.messages.order_by("-id")[:6])):
                response = message.response
                item = {"request": message.text, "intent": response.get("intent")}
                if response.get("change"):
                    change = response["change"]
                    item["preview"] = {k: change.get(k) for k in ("action", "target", "values")}
                history.append(item)
            model_context = {
                "orders": services.orders(request.user) if services.has_shop(request.user) else [],
                "categories": list(Category.objects.filter(is_active=True).values("slug", "name")[:50]),
                "history": history,
            }
        intent = planner.plan(data.validated_data["text"], c.context, catalog, **model_context)
        return Response(conversation.respond(request.user, c.uuid, channel=channel(request), plan=intent,
            **data.validated_data))


class Snapshot(Linked):
    def get(self, request):
        return Response({"products": services.products(request.user), "orders": services.orders(request.user)})


class Prepare(Linked):
    def post(self, request, uuid):
        data = ChangeInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(services.change_data(services.prepare_change(request.user, uuid, **data.validated_data)))


class Confirm(Linked):
    def post(self, request, uuid):
        data = ConfirmInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(services.change_data(services.confirm_change(request.user, uuid, channel(request))))
