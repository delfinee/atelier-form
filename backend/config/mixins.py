"""Abstract bases shared by every app.

Not an installed app -- these models are abstract, so Django never registers
them and they need no app_label.
"""

import uuid as uuid_lib

from django.db import models


class TimeStampedModel(models.Model):
    """UTC created/updated stamps. USE_TZ is on, so `auto_now*` writes UTC."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """A stable public identifier, so integer primary keys are never exposed."""

    uuid = models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True, db_index=True)

    class Meta:
        abstract = True
