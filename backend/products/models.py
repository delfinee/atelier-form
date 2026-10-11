"""Catalogue: categories, collections, makers, products, images and variants.

Inventory lives here and is authoritative. Nothing the browser sends about
price or stock is ever trusted -- see `orders.services`.
"""

from decimal import Decimal

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.text import slugify
from django.utils.translation import gettext_noop

from config.mixins import TimeStampedModel, UUIDModel
from imagery.resolver import PLACEHOLDER_PREFIX, image_url


class StockStatus(models.TextChoices):
    IN_STOCK = "in-stock", "In stock"
    LOW_STOCK = "low-stock", "Low stock"
    MADE_TO_ORDER = "made-to-order", "Made to order"
    SOLD_OUT = "sold-out", "Sold out"


class VariantGroup(models.TextChoices):
    COLOUR = "colour", "Colour"
    SIZE = "size", "Size"
    FINISH = "finish", "Finish"


class SluggedModel(UUIDModel, TimeStampedModel):
    """Anything the frontend routes to by slug."""

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, db_index=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:180]
        super().save(*args, **kwargs)


class Category(SluggedModel):
    """One of the four browsing categories: Ceramics, Textiles, Home, Gifts."""

    description = models.TextField(blank=True)
    tagline = models.CharField(max_length=200, blank=True)
    hero_image = models.CharField(max_length=200, blank=True)
    tile_image = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    # -- frontend template compatibility ---------------------------------
    @property
    def title(self) -> str:
        return self.name

    @property
    def kind(self) -> str:
        return "category"

    @property
    def hero(self) -> str:
        return self.hero_image

    @property
    def tile(self) -> str:
        return self.tile_image


class Collection(SluggedModel):
    """An editorial grouping. A product may sit in several."""

    description = models.TextField(blank=True)
    tagline = models.CharField(max_length=200, blank=True)
    story = models.TextField(blank=True)
    hero_image = models.CharField(max_length=200, blank=True)
    tile_image = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    @property
    def title(self) -> str:
        return self.name

    @property
    def kind(self) -> str:
        return "editorial"

    @property
    def hero(self) -> str:
        return self.hero_image

    @property
    def tile(self) -> str:
        return self.tile_image

    @property
    def featured(self) -> bool:
        return self.is_featured


class Maker(SluggedModel):
    """An artisan. The charter's differentiator -- every product names one."""

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name="maker_profile",
        null=True, blank=True, on_delete=models.SET_NULL,
        help_text="Seller account allowed to manage this maker and its products.",
    )
    discipline = models.CharField(max_length=120)
    location = models.CharField(max_length=120)
    since = models.CharField(max_length=10, blank=True)
    tagline = models.CharField(max_length=240, blank=True)
    short_bio = models.TextField(blank=True)
    biography = ArrayField(models.TextField(), default=list, blank=True,
                           help_text="One entry per paragraph.")
    process = ArrayField(models.TextField(), default=list, blank=True,
                         help_text="One entry per process step.")
    portrait = models.CharField(max_length=200, blank=True)
    studio_images = ArrayField(models.CharField(max_length=200), default=list, blank=True)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    @property
    def images(self) -> list:
        return list(self.studio_images or [])


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def with_related(self):
        return self.select_related("category", "maker").prefetch_related(
            "product_images", "product_variants", "collections"
        )

    def search(self, query: str):
        """Case-insensitive substring match over a denormalised blob.

        Deliberately ILIKE rather than `to_tsvector`: PostgreSQL's default
        text search configuration does not segment Simplified Chinese, so
        full-text search would silently fail to match 陶瓷杯 once the catalogue
        is localised (charter review §4.5). ILIKE handles CJK correctly. At
        this catalogue size the cost is irrelevant; the documented upgrade path
        is a pg_trgm GIN index, then zhparser/pg_jieba.
        """
        query = (query or "").strip()
        if not query:
            return self.none()
        return self.filter(search_blob__icontains=query)


class Product(SluggedModel):
    short_description = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    story = models.TextField(blank=True)

    price = models.DecimalField(max_digits=10, decimal_places=2,
                                validators=[MinValueValidator(Decimal("0.00"))])
    currency = models.CharField(max_length=3, default="CNY")

    category = models.ForeignKey(Category, related_name="products", on_delete=models.PROTECT)
    maker = models.ForeignKey(Maker, related_name="products", on_delete=models.PROTECT)
    collections = models.ManyToManyField(Collection, related_name="products", blank=True)

    materials = ArrayField(models.CharField(max_length=120), default=list, blank=True)
    dimensions = models.CharField(max_length=200, blank=True)
    care_instructions = models.TextField(blank=True)
    shipping_information = models.CharField(max_length=200, blank=True,
                                            help_text="Dispatch lead time shown on the product page.")

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_new_arrival = models.BooleanField(default=False)

    # -- inventory (authoritative) -----------------------------------------
    stock_quantity = models.PositiveIntegerField(
        default=0, help_text="Authoritative when the product has no variants.")
    is_made_to_order = models.BooleanField(
        default=False, help_text="Made to order: not limited by stock_quantity.")
    stock_status = models.CharField(max_length=20, choices=StockStatus.choices,
                                    default=StockStatus.IN_STOCK, db_index=True)

    sort_weight = models.IntegerField(default=0, help_text="Higher sorts earlier in Featured.")
    search_blob = models.TextField(blank=True, editable=False)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-sort_weight", "-created_at"]
        indexes = [
            models.Index(fields=["is_active", "is_featured"]),
            models.Index(fields=["is_active", "is_new_arrival"]),
            models.Index(fields=["price"]),
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["maker", "is_active"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name="product_price_non_negative"),
        ]

    # -- inventory helpers -------------------------------------------------
    @property
    def has_variants(self) -> bool:
        return self.product_variants.exists()

    @property
    def available_quantity(self) -> int:
        """Stock across variants when they exist, otherwise the product's own."""
        if self.is_made_to_order:
            return 10**6
        variants = list(self.product_variants.all())
        if variants:
            return sum(v.stock_quantity for v in variants if v.is_active)
        return self.stock_quantity

    def compute_stock_status(self) -> str:
        if self.is_made_to_order:
            return StockStatus.MADE_TO_ORDER
        available = self.available_quantity
        if available <= 0:
            return StockStatus.SOLD_OUT
        if available <= settings.COMMERCE["LOW_STOCK_THRESHOLD"]:
            return StockStatus.LOW_STOCK
        return StockStatus.IN_STOCK

    def refresh_stock_status(self, save: bool = True):
        """Denormalise stock into a filterable column.

        The shop filters on availability in SQL, which a derived property could
        not do, so the value is recomputed whenever stock moves.
        """
        status = self.compute_stock_status()
        if status != self.stock_status:
            self.stock_status = status
            if save:
                Product.objects.filter(pk=self.pk).update(stock_status=status)
        return status

    def build_search_blob(self) -> str:
        parts = [
            self.name, self.short_description, self.description, self.story,
            " ".join(self.materials or []), self.dimensions,
        ]
        if self.category_id:
            parts.append(self.category.name)
        if self.maker_id:
            parts.extend([self.maker.name, self.maker.discipline, self.maker.location])
        return " \n".join(p for p in parts if p)

    def save(self, *args, **kwargs):
        self.search_blob = self.build_search_blob()
        super().save(*args, **kwargs)

    # -- frontend template compatibility ---------------------------------
    # The templates were written against dicts; these keep them working
    # unchanged now that the same data comes from the ORM.
    @property
    def images(self) -> list:
        return [img.image for img in self.product_images.all()] or ["product-placeholder"]

    @property
    def variants(self) -> list:
        return list(self.product_variants.all())

    @property
    def featured(self) -> bool:
        return self.is_featured

    @property
    def new_arrival(self) -> bool:
        return self.is_new_arrival

    @property
    def care(self) -> str:
        return self.care_instructions

    @property
    def dispatch(self) -> str:
        return self.shipping_information

    @property
    def material_families(self) -> list:
        return material_families(self)

    def primary_image(self) -> str:
        first = self.product_images.first()
        return first.image if first else "product-placeholder"


class ProductImage(TimeStampedModel):
    """Images are a related table, never fixed columns on Product."""

    product = models.ForeignKey(Product, related_name="product_images", on_delete=models.CASCADE)
    image = models.CharField(
        max_length=200,
        help_text="Image name, e.g. 'product-speckled-breakfast-bowl-1'. Resolves to the "
                  f"photograph stored under that name in `imagery.SiteImage`, or to "
                  f"static/{PLACEHOLDER_PREFIX}/<name>.svg while none has been fetched.")
    alt_text = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order", "id"]
        indexes = [models.Index(fields=["product", "sort_order"])]

    def __str__(self):
        return f"{self.product.name} #{self.sort_order}"

    @property
    def url(self) -> str:
        return image_url(self.image)


class ProductVariant(UUIDModel, TimeStampedModel):
    """A single purchasable option -- colour, size or finish.

    Deliberately one axis per row rather than a full option-matrix engine: the
    frontend offers colour and size as independent chips, and nothing in it
    needs a cartesian SKU grid.
    """

    product = models.ForeignKey(Product, related_name="product_variants", on_delete=models.CASCADE)
    group = models.CharField(max_length=20, choices=VariantGroup.choices, default=VariantGroup.COLOUR)
    label = models.CharField(max_length=80)
    sku = models.CharField(max_length=64, unique=True)
    swatch = models.CharField(max_length=9, blank=True, help_text="Hex value, colour variants only.")
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                         validators=[MinValueValidator(Decimal("0.00"))])
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["group", "sort_order", "label"]
        constraints = [
            models.UniqueConstraint(fields=["product", "group", "label"], name="unique_variant_per_product"),
        ]
        indexes = [models.Index(fields=["product", "group"])]

    def __str__(self):
        return f"{self.product.name} — {self.label}"

    @property
    def unit_price(self):
        """Variant price wins when set; otherwise the product's."""
        return self.price_override if self.price_override is not None else self.product.price

    @property
    def available(self) -> bool:
        return self.is_active and (self.product.is_made_to_order or self.stock_quantity > 0)

    # Template compatibility: the mock data exposed a string id.
    @property
    def id_label(self) -> str:
        return f"{self.group}-{self.label.lower().replace(' ', '-')}"


# -- material families ----------------------------------------------------
# The raw materials list runs to ~40 strings, which is unusable as a filter, so
# the shop facets on a curated set of families instead.

MATERIAL_FAMILIES = [
    gettext_noop("Stoneware"), gettext_noop("Porcelain"), gettext_noop("Linen"),
    gettext_noop("Cotton"), gettext_noop("Wood"), gettext_noop("Brass"),
    gettext_noop("Rattan"), gettext_noop("Wax"),
]

MATERIAL_ALIASES = {
    "Stoneware": ["stoneware"], "Porcelain": ["porcelain"],
    "Linen": ["linen", "flax"], "Cotton": ["cotton"],
    "Wood": ["wood", "oak", "hardwood", "timber"], "Brass": ["brass"],
    "Rattan": ["rattan"], "Wax": ["wax", "beeswax", "soy", "rapeseed"],
}


def material_families(product) -> list:
    """Families a product belongs to, used for shop filtering."""
    import re

    blob = " ".join(product.materials or []).lower()
    # "wood-ash glaze" is a glaze, not a timber -- drop it before matching.
    blob = blob.replace("wood-ash", "ash")
    return [family for family in MATERIAL_FAMILIES
            if any(re.search(rf"\b{alias}", blob) for alias in MATERIAL_ALIASES[family])]
