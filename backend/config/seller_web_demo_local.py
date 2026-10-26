"""Loopback-only version of the isolated seller demo (no real credentials)."""
from .seller_public_demo import *  # noqa: F403

ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = None
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_NAME = 'seller_web_demo_session'
CSRF_COOKIE_NAME = 'seller_web_demo_csrf'
