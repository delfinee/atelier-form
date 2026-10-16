from dataclasses import dataclass
from datetime import timedelta
import hashlib
import secrets
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from .models import WechatSession


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class UnlinkedIdentity:
    pk: str
    is_authenticated: bool = True
    is_seller: bool = False
    is_active: bool = True


def issue_session(identity):
    token = secrets.token_urlsafe(32)
    expiry = timezone.now() + timedelta(hours=8)
    WechatSession.objects.filter(identity=identity, expires_at__lte=timezone.now()).delete()
    WechatSession.objects.create(identity=identity, token_hash=digest(token), expires_at=expiry)
    return {"token": token, "expires_at": expiry.isoformat(), "mode": identity.mode,
            "linked": bool(identity.user_id)}


class WechatAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != b"sellerwechat":
            return None
        if not settings.WECHAT_SELLER_ENABLED:
            raise PermissionDenied("The seller WeChat channel is disabled.")
        if len(header) != 2 or len(header[1]) > 128:
            raise AuthenticationFailed("Invalid WeChat session.")
        try:
            token = header[1].decode("ascii")
        except UnicodeDecodeError:
            raise AuthenticationFailed("Invalid WeChat session.") from None
        session = WechatSession.objects.select_related("identity__user").filter(
            token_hash=digest(token), expires_at__gt=timezone.now()).first()
        if session is None:
            raise AuthenticationFailed("WeChat session expired. Sign in again.")
        identity = session.identity
        if identity.mode == "developer" and not (settings.DEBUG and settings.WECHAT_SELLER_DEV_LOGIN):
            raise AuthenticationFailed("Developer sessions are disabled.")
        if identity.user_id:
            if not identity.user.is_active:
                raise AuthenticationFailed("This account is disabled.")
            return identity.user, session
        return UnlinkedIdentity(str(identity.uuid)), session

    def authenticate_header(self, request):
        return "SellerWechat"


def channel(request):
    if isinstance(request.auth, WechatSession):
        return request.auth.identity.mode
    return "web"


def require_linked(request):
    if not isinstance(request.user, get_user_model()):
        raise PermissionDenied("Link your WeChat session to your website account first.")
