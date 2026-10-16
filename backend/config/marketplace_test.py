"""Full regression uses the baseline cookie contract; phone tests override theirs."""
from .seller_agent_local import *  # noqa: F403
SESSION_COOKIE_NAME = 'sessionid'
CSRF_COOKIE_NAME = 'csrftoken'
