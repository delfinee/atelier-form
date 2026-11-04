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
from .i18n import language
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


class SnapshotThrottle(UserRateThrottle):
    scope = "seller_agent_snapshot"
    rate = "120/min"


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
            "onboarding": conversation.onboarding_guide(getattr(request, "seller_shared_demo", False)),
            "shared_demo": getattr(request, "seller_shared_demo", False),
            "engine": "deepseek" if planner.enabled(getattr(request, "seller_shared_demo", False)) else "guided"})


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
        demo_login = getattr(request, 'seller_demo_login', None)
        return Response({"linked": linked, "is_seller": services.has_shop(request.user) if linked else False,
            "account": demo_login.email if demo_login else request.user.email if linked else None,
            "seller_name": demo_login.full_name if demo_login else None,
            "channel": channel(request),
            "onboarding": conversation.onboarding_guide(getattr(request, "seller_shared_demo", False))})


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
            for c in Conversation.objects.filter(user=request.user, language=language()).order_by("-id")[:30]]})

    def post(self, request):
        c = Conversation.objects.create(user=request.user, language=language())
        return Response({"id":str(c.uuid)}, status=201)


class Detail(Linked):
    def get(self, request, uuid):
        c = services.conversation_for(request.user, uuid)
        return Response({"id":str(c.uuid), "messages":[{"text":m.text,"response":m.response,"channel":m.channel}
            for m in c.messages.all()], "changes":[services.change_data(d) for d in c.changes.select_related('operation').order_by("id")]})


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
        shared_demo = getattr(request, "seller_shared_demo", False)
        if planner.enabled(shared_demo):
            history = []
            changes = {str(change.uuid): services.change_data(change) for change in c.changes.order_by('-id')[:20]}
            for message in reversed(list(c.messages.order_by("-id")[:10])):
                response = message.response
                item = {"request": message.text, "intent": response.get("intent"),
                        "reply": response.get('reply', '')[:1600]}
                if response.get("change"):
                    change = changes.get(response['change']['id'], response['change'])
                    item["preview"] = {k: change.get(k) for k in ("action", "target", "values")}
                    item['preview']['status'] = change.get('status')
                    if change.get('result'):
                        item['result'] = {k: change['result'].get(k) for k in ('product', 'order') if k in change['result']}
                history.append(item)
            model_context = {
                "orders": services.orders(request.user) if services.has_shop(request.user) else [],
                "categories": list(Category.objects.filter(is_active=True).values("slug", "name")[:50]),
                "history": history,
            }
        intent = planner.plan(data.validated_data["text"], c.context, catalog,
                              shared_demo=shared_demo, language=language(), **model_context)
        return Response(conversation.respond(request.user, c.uuid, channel=channel(request), plan=intent,
            **data.validated_data))


class Snapshot(Linked):
    # Active clients poll the shared snapshot; chat remains independently bounded.
    throttle_classes = [SnapshotThrottle]
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
