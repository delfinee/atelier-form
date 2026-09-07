"""Real photography, stored as bytes in PostgreSQL.

The frontend addresses every image by a *name* -- `hero-studio-table`,
`product-hand-thrown-stoneware-mug-1`, `maker-lu-wenjing`. Those names were
already the filenames of the generated SVG placeholders, and they are already
what `products` and `content` rows store in their image columns. Keeping the
name as the key means swapping a placeholder for a photograph is a row insert
and nothing else: no template, column or fixture changes.

Bytes live in a `bytea` column rather than on disk so a single `pg_dump`
carries the whole site. That is a deliberate trade -- it inflates the database
and its backups -- and the one rule that keeps it affordable is that `data` is
*never* selected unless it is about to be written to a response. The default
manager enforces that by deferring the column; `SiteImage.objects.with_data()`
is the only way to load it.
"""

from __future__ import annotations

import hashlib

from django.db import models

from config.mixins import TimeStampedModel

# Target pixel dimensions per aspect ratio. These mirror the ratios the layout
# was built against (see `frontend.templatetags.frontend_extras.RATIOS`),
# so a fetched photograph lands in exactly the box the placeholder occupied.
RATIOS: dict[str, tuple[int, int]] = {
    "wide": (1600, 900),        # hero, collection banners        16:9
    "ultrawide": (1800, 760),   # full-bleed editorial feature   ~21:9
    "landscape": (1400, 933),   # journal cards, storytelling      3:2
    "portrait": (800, 1000),    # product imagery, categories      4:5
    "tall": (750, 1000),        # maker portraits                  3:4
    "square": (1000, 1000),     # gallery tiles                    1:1
}

DEFAULT_RATIO = "portrait"


class SiteImageQuerySet(models.QuerySet):
    def with_data(self):
        """Re-select the deferred `data` column. Only the serving view needs it."""
        return self.defer(None)


class SiteImageManager(models.Manager.from_queryset(SiteImageQuerySet)):
    def get_queryset(self):
        # Deferring here rather than at each call site means no amount of
        # careless querying can accidentally drag megabytes of JPEG into a
        # list page.
        return super().get_queryset().defer("data")


class SiteImage(TimeStampedModel):
    """One photograph, keyed by the name the templates and rows already use."""

    name = models.SlugField(
        max_length=200, unique=True,
        help_text="Placeholder key, e.g. 'product-hand-thrown-stoneware-mug-1'.",
    )
    ratio = models.CharField(max_length=20, default=DEFAULT_RATIO,
                             choices=[(k, k) for k in RATIOS])
    alt_text = models.CharField(max_length=300, blank=True)
    search_query = models.CharField(max_length=300, blank=True,
                                    help_text="Terms used to find this image.")

    data = models.BinaryField(help_text="Encoded image bytes (bytea).")
    content_type = models.CharField(max_length=40, default="image/jpeg")
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    byte_size = models.PositiveIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True,
                                help_text="SHA-256 of `data`; used as ETag and URL version.")

    # -- provenance -------------------------------------------------------
    # Most of what Openverse returns is CC-licensed rather than public domain,
    # so the terms travel with the bytes and /credits/ renders them. Dropping
    # these columns would make the images unusable, not merely undocumented.
    provider = models.CharField(max_length=60, blank=True)
    source_id = models.CharField(max_length=100, blank=True)
    source_url = models.URLField(max_length=500, blank=True,
                                 help_text="Page the image was found on.")
    source_title = models.CharField(max_length=300, blank=True)
    creator = models.CharField(max_length=200, blank=True)
    creator_url = models.URLField(max_length=500, blank=True)
    license = models.CharField(max_length=40, blank=True)
    license_version = models.CharField(max_length=20, blank=True)
    license_url = models.URLField(max_length=500, blank=True)
    attribution = models.TextField(blank=True, help_text="Ready-made credit line.")
    fetched_at = models.DateTimeField(null=True, blank=True)

    objects = SiteImageManager()

    class Meta:
        ordering = ["name"]
        verbose_name = "site image"
        verbose_name_plural = "site images"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Only re-hash when the bytes are actually in hand. Touching `self.data`
        # on a deferred instance -- an admin edit, a metadata fix -- would fetch
        # a megabyte from the database purely to compute a digest that has not
        # changed.
        if "data" not in self.get_deferred_fields() and self.data is not None:
            payload = bytes(self.data)
            self.checksum = hashlib.sha256(payload).hexdigest()
            self.byte_size = len(payload)

            # `update_or_create` names the fields it is writing, and these two
            # are derived here rather than passed in, so they are absent from
            # that list. Without this they silently keep describing the previous
            # image: the ETag stops changing and the stored length stops
            # matching the stored bytes.
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"checksum", "byte_size"}
        super().save(*args, **kwargs)

    @property
    def version(self) -> str:
        """Short cache-busting token. Changing bytes changes the URL."""
        return self.checksum[:12]

    @property
    def url(self) -> str:
        from .resolver import image_url

        return image_url(self.name)

    @property
    def needs_attribution(self) -> bool:
        """CC0 and public-domain marks carry no attribution requirement."""
        return self.license.lower() not in {"", "cc0", "pdm"}
