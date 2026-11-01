"""Provider keys remain on the server, encrypted with the deployment secret."""
import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import DatabaseError
from .models import ProviderSecret


def _cipher(secret):
    key = hmac.new(secret.encode(), b'atelier:seller-provider:v1', hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_key(value):
    return _cipher(settings.SECRET_KEY).encrypt(value.encode()).decode()


def api_key():
    if settings.SELLER_AGENT_API_KEY:
        return settings.SELLER_AGENT_API_KEY
    try:
        stored = ProviderSecret.objects.filter(provider='deepseek').values_list('encrypted_key', flat=True).first()
    except DatabaseError:
        return ''
    if not stored:
        return ''
    for secret in [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]:
        try:
            return _cipher(secret).decrypt(stored.encode()).decode()
        except (InvalidToken, ValueError, UnicodeError):
            continue
    return ''
