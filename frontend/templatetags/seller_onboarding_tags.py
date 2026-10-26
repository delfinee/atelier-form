"""Template helpers for seller onboarding navigation."""
from django import template
from django.core.exceptions import PermissionDenied

from accounts import seller_onboarding

register = template.Library()


@register.simple_tag(takes_context=True)
def can_review_seller_applications(context) -> bool:
    """Whether to show the review-queue link: the service's own reviewer rule.

    Only a link; the review pages check again on every request.
    """
    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None or not (getattr(user, "is_admin", False) or getattr(user, "is_superuser", False)):
        return False  # skips the database check for everyone who cannot be a reviewer
    try:
        seller_onboarding.require_reviewer(user)
    except PermissionDenied:
        return False
    return True
