"""Phone preview behind an HTTPS tunnel; never enable developer identities."""
from .settings import *  # noqa: F403

DEBUG = False
SELLER_AGENT_ENABLED = True
# Opt in using the private server environment; never bundle keys in the client.
SELLER_AGENT_USE_LLM = env.bool('SELLER_AGENT_USE_LLM', default=False)
WECHAT_SELLER_ENABLED = True
WECHAT_SELLER_DEV_LOGIN = False
ROOT_URLCONF = 'config.seller_phone_urls'
LANGUAGE_CODE = 'en'
LANGUAGES = [('en', 'English')]
SELLER_PHONE_PREVIEW = True
LOGIN_URL = '/account/login/'
LOGIN_REDIRECT_URL = '/seller/ai/'
LOGOUT_REDIRECT_URL = '/account/login/'
SESSION_COOKIE_NAME = 'seller_phone_session'
CSRF_COOKIE_NAME = 'seller_phone_csrf'
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 0  # Temporary host, not a permanent production deployment.
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
STATIC_ROOT = BASE_DIR / '.seller-agent-runtime' / 'phone-static'
STORAGES = {**STORAGES, 'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
EMAIL_SENDER_CLASS = 'content.services.ConsoleEmailSender'
TEMPLATES = [{**engine, 'OPTIONS': {**engine['OPTIONS'], 'context_processors': [
    processor for processor in engine['OPTIONS']['context_processors']
    if processor != 'frontend.context_processors.frontend']}} for engine in TEMPLATES]
