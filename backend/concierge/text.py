"""The local desk is Chinese; the shared team sandbox is English."""
from django.conf import settings


def text(chinese, english):
    return english if settings.PUBLIC_CONCIERGE_DEMO else chinese
