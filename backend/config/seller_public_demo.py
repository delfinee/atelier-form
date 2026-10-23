"""Disposable, isolated website demo. Never point this at a real shop database."""
import os
from django.core.exceptions import ImproperlyConfigured
from .seller_phone import *  # noqa: F403

if DATABASES['default']['NAME'] != 'atelier_public_demo':
    raise ImproperlyConfigured('The public demo requires its own atelier_public_demo database.')
if len(os.environ.get('DJANGO_SECRET_KEY', '')) < 50:
    raise ImproperlyConfigured('Configure a unique demo session secret.')
SELLER_PUBLIC_DEMO = True
SELLER_PHONE_PREVIEW = False
WECHAT_SELLER_ENABLED = False
WECHAT_SELLER_DEV_LOGIN = False
WECHAT_APP_SECRET = ''
# Opt in per deployment. Keys are loaded from the private server env only.
SELLER_AGENT_USE_LLM = env.bool('SELLER_AGENT_USE_LLM', default=False)
SELLER_AGENT_API_KEY = env.str('SELLER_AGENT_API_KEY', default='')
ROOT_URLCONF = 'config.seller_public_demo_urls'
ALLOWED_HOSTS = ['.trycloudflare.com', 'localhost', '127.0.0.1', 'app']
LOGIN_URL = '/'
SESSION_COOKIE_NAME = '__Host-seller-demo'
CSRF_COOKIE_NAME = '__Host-seller-demo-csrf'
SESSION_COOKIE_AGE = 86400
SESSION_COOKIE_HTTPONLY = True
STATIC_ROOT = BASE_DIR / 'staticfiles'
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.db.DatabaseCache', 'LOCATION': 'seller_cache'}}
REST_FRAMEWORK = {**REST_FRAMEWORK, 'NUM_PROXIES': 1}
MIDDLEWARE = [*MIDDLEWARE, 'seller_agent.public_demo.DemoGuard']
