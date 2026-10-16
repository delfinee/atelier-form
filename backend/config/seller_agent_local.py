"""Loopback-only development; business data stays in the configured platform DB."""
from .settings import *  # noqa: F403

DEBUG=True
ALLOWED_HOSTS=['localhost','127.0.0.1']
SELLER_AGENT_ENABLED=True
SELLER_AGENT_USE_LLM=False  # Local acceptance tests never spend provider quota.
WECHAT_SELLER_ENABLED=True
WECHAT_SELLER_DEV_LOGIN=True
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
SESSION_COOKIE_NAME='seller_agent_session'
CSRF_COOKIE_NAME='seller_agent_csrf'
STATIC_ROOT=BASE_DIR/'.seller-agent-runtime'/'static'
STORAGES={**STORAGES,'staticfiles':{'BACKEND':'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend'
EMAIL_SENDER_CLASS='content.services.ConsoleEmailSender'
