"""Seller-only deployment. Required configuration fails closed at startup."""
import os
import re
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured
from .seller_phone import *  # noqa: F403


def required(name):
    value = os.environ.get(name, '').strip()
    if not value or value.startswith('REPLACE_'):
        raise ImproperlyConfigured(f'{name} must be configured for production.')
    return value


origin = required('SELLER_PUBLIC_ORIGIN')
parsed = urlsplit(origin)
if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
        or parsed.port or parsed.path not in ('', '/') or parsed.query or parsed.fragment
        or parsed.hostname.endswith(('.invalid', '.test', '.localhost', '.trycloudflare.com'))
        or not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', parsed.hostname)
        or parsed.hostname.startswith('replace')):
    raise ImproperlyConfigured('SELLER_PUBLIC_ORIGIN requires a permanent HTTPS domain.')
if os.environ.get('APP_DOMAIN') and os.environ['APP_DOMAIN'] != parsed.hostname:
    raise ImproperlyConfigured('APP_DOMAIN and SELLER_PUBLIC_ORIGIN must name the same host.')

SECRET_KEY = required('DJANGO_SECRET_KEY')
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured('Use a random DJANGO_SECRET_KEY of at least 50 characters.')
WECHAT_APP_ID = required('WECHAT_APP_ID')
WECHAT_APP_SECRET = required('WECHAT_APP_SECRET')
if not re.fullmatch(r'wx[0-9a-f]{16}', WECHAT_APP_ID) or not re.fullmatch(r'[0-9a-f]{32}', WECHAT_APP_SECRET):
    raise ImproperlyConfigured('Configure the real Mini Program AppID and AppSecret.')
required('DATABASE_URL')
SELLER_OPERATOR = required('SELLER_OPERATOR')
SELLER_CONTACT_EMAIL = required('SELLER_CONTACT_EMAIL')
if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', SELLER_CONTACT_EMAIL):
    raise ImproperlyConfigured('SELLER_CONTACT_EMAIL must be a monitored support email.')

DEBUG = False
SELLER_PHONE_PREVIEW = False
SELLER_PRODUCTION = True
SELLER_AGENT_USE_LLM = False
WECHAT_SELLER_DEV_LOGIN = False
ROOT_URLCONF = 'config.seller_production_urls'
SITE_URL = origin.rstrip('/')
ALLOWED_HOSTS = [parsed.hostname]
CSRF_TRUSTED_ORIGINS = [SITE_URL]
CORS_ALLOWED_ORIGINS = [SITE_URL]
SESSION_COOKIE_NAME = '__Host-seller-session'
CSRF_COOKIE_NAME = '__Host-seller-csrf'
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_REFERRER_POLICY = 'same-origin'
STATIC_ROOT = BASE_DIR / 'staticfiles'
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
                     'LOCATION': 'seller_cache', 'TIMEOUT': 300}}
REST_FRAMEWORK = {**REST_FRAMEWORK, 'NUM_PROXIES': 1}
MIDDLEWARE = [*MIDDLEWARE, 'seller_agent.release_views.PrivateResponses']
