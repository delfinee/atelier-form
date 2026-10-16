"""WeChat transport and explicit account linking; never provisions a seller."""
from datetime import timedelta
from ipaddress import ip_address
import secrets
import requests
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError, PermissionDenied, AuthenticationFailed
from .auth import digest, issue_session
from .models import WechatIdentity, WechatSession, LinkTicket, UsedLoginCode


class Unavailable(APIException):
    status_code = 503
    default_detail = "WeChat is not connected. Configure an AppID and AppSecret on the server first."


def local_developer_allowed(request):
    try:
        loopback = ip_address(request.META.get("REMOTE_ADDR", "")).is_loopback
    except ValueError:
        loopback = False
    return (settings.DEBUG and settings.WECHAT_SELLER_DEV_LOGIN and loopback
            and request.get_host().split(":")[0] in ("127.0.0.1", "localhost"))


def developer_login(request):
    if not local_developer_allowed(request):
        raise PermissionDenied("Developer login is available only on this computer.")
    identity = WechatIdentity.objects.create(app_id="local-developer", openid_hash=digest(secrets.token_urlsafe(32)),
                                              mode="developer")
    return issue_session(identity)


def login(code):
    if not (settings.WECHAT_APP_ID and settings.WECHAT_APP_SECRET):
        raise Unavailable()
    code_hash = digest(settings.WECHAT_APP_ID + ":" + code)
    if UsedLoginCode.objects.filter(code_hash=code_hash).exists():
        raise AuthenticationFailed("This WeChat login code has already been used.")
    try:
        response = requests.get("https://api.weixin.qq.com/sns/jscode2session", params={
            "appid": settings.WECHAT_APP_ID, "secret": settings.WECHAT_APP_SECRET,
            "js_code": code, "grant_type": "authorization_code"}, timeout=(5, 15))
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        raise Unavailable("WeChat login could not be verified. Please retry.") from None
    if isinstance(data, dict) and data.get("errcode") == 40125:
        raise Unavailable("WeChat rejected the server AppSecret. Ask the app administrator to update it.")
    if not isinstance(data, dict) or data.get("errcode"):
        raise AuthenticationFailed("WeChat rejected this login code. Please sign in again.")
    if not isinstance(data.get("openid"), str) or not 1 <= len(data["openid"]) <= 128 or not data.get("session_key"):
        raise Unavailable("WeChat returned an invalid login response.")
    with transaction.atomic():
        UsedLoginCode.objects.filter(expires_at__lt=timezone.now()).delete()
        _, created = UsedLoginCode.objects.get_or_create(code_hash=code_hash,
            defaults={"expires_at": timezone.now()+timedelta(minutes=15)})
        if not created:
            raise AuthenticationFailed("This WeChat login code has already been used.")
        identity, _ = WechatIdentity.objects.get_or_create(app_id=settings.WECHAT_APP_ID,
            openid_hash=digest(settings.WECHAT_APP_ID+":"+data["openid"]), defaults={"mode": "wechat"})
        # Session keys and OpenIDs are neither logged nor sent to clients.
        return issue_session(identity)


@transaction.atomic
def start_link(session):
    identity = WechatIdentity.objects.select_for_update().get(pk=session.identity_id)
    if identity.user_id:
        raise ValidationError("This WeChat identity is already linked. Unlink it from the website before changing accounts.")
    token = secrets.token_urlsafe(32)
    LinkTicket.objects.create(identity=identity, token_hash=digest(token),
                              expires_at=timezone.now()+timedelta(minutes=5))
    return {"token": token, "verification_code": digest(token)[:6].upper(), "expires_in": 300}


@transaction.atomic
def approve_link(user, token, verification_code):
    if not secrets.compare_digest(digest(token)[:6].upper(), verification_code.upper()):
        raise ValidationError("Enter the six-character code shown in your own Mini Program session.")
    # Consistent locking order: identity before ticket, including simultaneous approvals.
    candidate = get_object_or_404(LinkTicket, token_hash=digest(token))
    identity = WechatIdentity.objects.select_for_update().get(pk=candidate.identity_id)
    ticket = LinkTicket.objects.select_for_update().get(pk=candidate.pk)
    if ticket.used_at or ticket.expires_at <= timezone.now():
        raise ValidationError("This account-link request expired or was already used.")
    if identity.user_id:
        raise PermissionDenied("This WeChat identity is already linked to an account.")
    if not user.is_active:
        raise PermissionDenied("This website account is disabled.")
    identity.user = user
    identity.save(update_fields=["user", "updated_at"])
    LinkTicket.objects.filter(identity=identity, used_at__isnull=True).update(used_at=timezone.now())
    return {"linked": True, "account": user.email, "mode": identity.mode}


@transaction.atomic
def unlink(user, uuid):
    identity = get_object_or_404(WechatIdentity.objects.select_for_update(), uuid=uuid, user=user)
    WechatSession.objects.filter(identity=identity).delete()
    LinkTicket.objects.filter(identity=identity, used_at__isnull=True).update(used_at=timezone.now())
    identity.user = None
    identity.save(update_fields=["user", "updated_at"])
