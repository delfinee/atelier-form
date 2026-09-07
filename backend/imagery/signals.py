"""Keep the resolver's name->checksum map honest."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import SiteImage
from .resolver import invalidate_index


@receiver([post_save, post_delete], sender=SiteImage)
def _drop_index(sender, **kwargs):
    invalidate_index()
