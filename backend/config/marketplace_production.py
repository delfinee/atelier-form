"""Permanent-domain storefront and WeChat API sharing the production database."""
from .seller_production import *  # noqa: F403
from .settings import TEMPLATES as STOREFRONT_TEMPLATES
ROOT_URLCONF = 'config.marketplace_urls'
TEMPLATES = STOREFRONT_TEMPLATES
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
BUYER_ASSISTANT_ENABLED = True
CONCIERGE_DEMO = False
TRUST_PROXY_CLIENT_IP = True  # Caddy overwrites this header, and app has no host port.
