"""One local database for the buyer storefront and seller Mini Program."""
from .seller_agent_local import *  # noqa: F403
ROOT_URLCONF = 'config.marketplace_urls'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
BUYER_ASSISTANT_ENABLED = True
CONCIERGE_DEMO = False  # Historical mock order console is retained, not auto-enabled.
