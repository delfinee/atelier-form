"""Public group acceptance site. Synthetic catalogue; mock payments only."""
import os
from django.core.exceptions import ImproperlyConfigured
from .settings import *  # noqa: F403

if DATABASES['default']['NAME'] != 'atelier_marketplace_demo' or len(os.environ.get('DJANGO_SECRET_KEY', '')) < 50:
    raise ImproperlyConfigured('Use a dedicated atelier_marketplace_demo database and random secret.')
DEBUG = False
ROOT_URLCONF = 'config.marketplace_urls'
MARKETPLACE_PUBLIC_DEMO = True
BUYER_AI_USE_LLM = env.bool('BUYER_AI_USE_LLM', default=False)
DEEPSEEK_API_KEY = env.str('DEEPSEEK_API_KEY', default='')
SELLER_AGENT_ENABLED = True
SELLER_AGENT_USE_LLM = False
WECHAT_SELLER_ENABLED = False
WECHAT_SELLER_DEV_LOGIN = False
WECHAT_APP_SECRET = ''
CONCIERGE_DEMO = False
PAYMENT_BACKEND = 'payments.services.MockPaymentProvider'
ALLOWED_HOSTS = ['.trycloudflare.com', 'localhost', '127.0.0.1', 'app']
LANGUAGE_CODE = 'en'
LANGUAGES = [('en', 'English'), ('zh-hans', '简体中文')]
STATIC_ROOT = BASE_DIR / 'staticfiles'
SESSION_COOKIE_NAME = '__Host-marketplace-demo'
CSRF_COOKIE_NAME = '__Host-marketplace-csrf'
SESSION_COOKIE_AGE = 86400
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
CACHES = {'default': {'BACKEND':'django.core.cache.backends.db.DatabaseCache', 'LOCATION':'marketplace_cache'}}
MIDDLEWARE = [*MIDDLEWARE, 'concierge.buyer_views.DemoBoundaries']
MIDDLEWARE.insert(MIDDLEWARE.index('django.middleware.locale.LocaleMiddleware'), 'concierge.buyer_views.DemoLanguage')
