import hashlib
from dataclasses import dataclass
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from .models import CustomerSession


def digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CustomerPrincipal:
    pk: str
    is_authenticated: bool = True
    is_active: bool = True
    is_seller: bool = False
    is_staff: bool = False
    is_superuser: bool = False


class CustomerAuthentication(BaseAuthentication):
    """A customer token never resolves to the merchant's Django user."""
    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != b"customer":
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("Invalid customer session.")
        try:
            token = parts[1].decode("ascii")
        except UnicodeDecodeError:
            raise AuthenticationFailed("Invalid customer session.") from None
        access = CustomerSession.objects.select_related("conversation__maker__owner").filter(
            token_hash=digest(token), revoked=False, expires_at__gt=timezone.now(),
            conversation__maker__is_active=True, conversation__maker__owner__is_active=True).first()
        if access is None:
            raise AuthenticationFailed("This preview session has expired. Request a new invitation from the seller.")
        return CustomerPrincipal(str(access.uuid)), access

    def authenticate_header(self, request):
        return "Customer"
