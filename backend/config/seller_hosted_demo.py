"""Always-on, isolated seller demo behind the existing HTTPS gateway."""
import os
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured
from .seller_public_demo import *  # noqa: F403

origin = os.environ.get('SELLER_DEMO_ORIGIN', '').strip().rstrip('/')
parsed = urlsplit(origin)
if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
        or parsed.port or parsed.path or parsed.query or parsed.fragment
        or parsed.hostname in {'localhost', '127.0.0.1'}
        or parsed.hostname.endswith(('.invalid', '.test', '.trycloudflare.com'))):
    raise ImproperlyConfigured('SELLER_DEMO_ORIGIN must be a permanent HTTPS origin.')

SITE_URL = origin
ALLOWED_HOSTS = [parsed.hostname]
CSRF_TRUSTED_ORIGINS = [origin]
CORS_ALLOWED_ORIGINS = [origin]
SESSION_COOKIE_NAME = '__Host-atelier-demo'
CSRF_COOKIE_NAME = '__Host-atelier-demo-csrf'
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
SECURE_HSTS_SECONDS = 86400
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
TRUST_PROXY_CLIENT_IP = True
REST_FRAMEWORK = {**REST_FRAMEWORK, 'NUM_PROXIES': 1}
