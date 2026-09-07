"""What to photograph, and what to search for.

Every image name the site renders is derived here from the rows PostgreSQL
already holds -- product names and materials, maker disciplines, article titles,
category taglines -- plus a short fixed list for the handful of editorial slots
that belong to the site's own copy rather than to any record.

Two constraints shape the design:

* Openverse ANDs every search term, so `ceramicist artisan craftsperson
  workshop` matches nothing while `ceramicist` matches hundreds. Each group
  therefore carries a *ladder* of queries in descending specificity, and the
  fetcher walks down it until it has enough candidates.
* The anonymous quota is 200 requests a day. Names are grouped so one search
  feeds several slots -- a product needs four frames -- which turns 130 images
  into roughly 42 groups.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import DEFAULT_RATIO, RATIOS

# Remove generic commercial words that weaken image searches.
_NOISE = {"set", "the", "a", "an", "of", "and", "with", "for", "in", "&",
          "collection", "small", "large", "essentials",
          # Remove quantities and collectives because the last word is the subject.
          "pair", "two", "three", "four", "duo", "trio", "pack", "bundle",
          "kit", "piece", "pieces"}

# Map maker disciplines to terms used by image libraries.
_DISCIPLINE_TERMS = {
    "ceramicist": ("potter wheel", "pottery"),
    "weaver": ("weaving loom", "weaving"),
    "woodworker": ("woodworking workshop", "woodworking"),
    "candlemaker": ("candle making", "candle"),
    "textile": ("weaving loom", "weaving"),
}

# Map each category to a specific term and a broad fallback.
_CATEGORY_TERMS = {
    "ceramics": ("ceramic", "pottery"),
    "textiles": ("linen", "textile"),
    "home": ("wooden", "woodwork"),
    "gifts": ("handmade", "candle"),
}


@dataclass(frozen=True)
class Slot:
    """One stored image: the name templates ask for, its box, its alt text."""

    name: str
    ratio: str
    alt: str = ""

    def __post_init__(self):
        if self.ratio not in RATIOS:
            raise ValueError(f"{self.name}: unknown ratio {self.ratio!r}")


@dataclass
class Group:
    """Slots that share one search ladder, each taking a different result."""

    key: str
    queries: list[str]
    slots: list[Slot] = field(default_factory=list)

    @property
    def query(self) -> str:
        """The most specific query, recorded on each row for traceability."""
        return self.queries[0] if self.queries else ""


def _words(text: str) -> list[str]:
    out: list[str] = []
    for word in str(text or "").replace("·", " ").replace("-", " ").replace("&", " ").split():
        cleaned = word.strip(",.—–()\"'").lower()
        if cleaned and cleaned not in _NOISE and cleaned not in out:
            out.append(cleaned)
    return out


def _ladder(*steps: str) -> list[str]:
    """Dedupe and drop empties, preserving the specific-to-broad order."""
    ladder: list[str] = []
    for step in steps:
        step = " ".join(step.split())
        if step and step not in ladder:
            ladder.append(step)
    return ladder


# Define editorial image slots that have no database row.
def _editorial() -> list[Group]:
    gallery_ratios = ("square", "portrait", "landscape", "square", "portrait", "landscape")
    return [
        Group("studio", _ladder("pottery studio", "potter workshop", "workshop"), [
            Slot("hero-studio-table", "wide", "A studio table set with handmade ceramics"),
            Slot("story-hero", "ultrawide", "The Atelier Form studio"),
            Slot("contact-studio", "landscape", "The studio doorway"),
            Slot("story-workshop", "landscape", "In the workshop"),
        ]),
        Group("hands", _ladder("potter wheel", "throwing clay", "pottery hands"), [
            Slot("story-hands", "portrait", "Hands at the wheel"),
            Slot("process-crafted", "portrait", "At the wheel"),
        ]),
        Group("materials", _ladder("raw clay", "natural dye", "clay"), [
            Slot("story-materials", "landscape", "Raw materials"),
            Slot("process-designed", "portrait", "Sketches and samples"),
        ]),
        Group("interior", _ladder("wooden table", "minimal interior", "interior"), [
            Slot("story-interior", "landscape", "A quiet interior"),
            Slot("journal-hero", "wide", "From the journal"),
        ]),
        Group("finishing", _ladder("wrapping paper craft", "packing pottery", "brown paper"), [
            Slot("process-finished", "portrait", "Finishing and packing"),
        ]),
        Group("gallery", _ladder("still life pottery", "handmade ceramics", "ceramics"), [
            Slot(f"gallery-{i}", gallery_ratios[i - 1], f"At home {i:02d}")
            for i in range(1, 7)
        ]),
    ]


def _catalogue() -> list[Group]:
    """Groups built from the catalogue tables."""
    from content.models import Article
    from products.models import Category, Collection, Maker, Product

    groups: list[Group] = []

    for category in Category.objects.all():
        qualifier, fallback = _CATEGORY_TERMS.get(category.slug, ("handmade", "craft"))
        subject = " ".join(_words(category.name)[:1]) or fallback
        slots = []
        if category.tile_image:
            slots.append(Slot(category.tile_image, "portrait", category.name))
        if category.hero_image:
            slots.append(Slot(category.hero_image, "wide", category.tagline or category.name))
        if slots:
            groups.append(Group(
                f"category-{category.slug}",
                _ladder(f"handmade {subject}", subject, fallback),
                slots,
            ))

    for collection in Collection.objects.all():
        subject = " ".join(_words(collection.name)[:1])
        slots = []
        if collection.hero_image:
            # Use a full-bleed ratio for Earth and wide banners elsewhere.
            ratio = "ultrawide" if collection.hero_image == "collection-earth" else "wide"
            slots.append(Slot(collection.hero_image, ratio, collection.name))
        if collection.tile_image and collection.tile_image != collection.hero_image:
            slots.append(Slot(collection.tile_image, "portrait", collection.name))
        if slots:
            groups.append(Group(
                f"collection-{collection.slug}",
                _ladder(f"{subject} pottery", f"handmade {subject}", "handmade ceramics"),
                slots,
            ))

    for maker in Maker.objects.all():
        discipline = _words(maker.discipline)
        primary = discipline[0] if discipline else "artisan"
        specific, broad = _DISCIPLINE_TERMS.get(primary, (f"{primary} workshop", primary))
        slots = []
        if maker.portrait:
            slots.append(Slot(maker.portrait, "tall", f"{maker.name}, {maker.discipline}"))
        for index, studio in enumerate(maker.studio_images or []):
            slots.append(Slot(studio, "landscape",
                              f"{maker.name} at work" if index == 0 else f"{maker.name}'s studio"))
        if slots:
            groups.append(Group(
                f"maker-{maker.slug}",
                _ladder(specific, broad, "craft workshop"),
                slots,
            ))

    products = (Product.objects.all()
                .select_related("category")
                .prefetch_related("product_images"))
    for product in products:
        qualifier, fallback = _CATEGORY_TERMS.get(product.category.slug, ("handmade", "craft"))
        # Use the product head noun and the material's most specific term.
        name_words = _words(product.name)
        head = name_words[-1] if name_words else fallback
        material_words = _words((product.materials or [""])[0])
        material = material_words[-1] if material_words else qualifier

        slots = [
            Slot(image.image, "portrait", image.alt_text or product.name)
            for image in product.product_images.all()
        ]
        # Add the story image slot rendered directly by the product template.
        slots.append(Slot(f"story-{product.slug}", "landscape", f"Making the {product.name}"))
        groups.append(Group(
            f"product-{product.slug}",
            # Avoid bare nouns that image libraries interpret too broadly.
            _ladder(f"{material} {head}", f"{qualifier} {head}",
                    f"handmade {fallback}", fallback),
            slots,
        ))

    for article in Article.objects.all():
        if not article.cover_image:
            continue
        title_words = _words(article.title)
        # Use the final title words as the article subject.
        subject = " ".join(title_words[-2:]) if len(title_words) > 1 else "".join(title_words)
        groups.append(Group(
            f"journal-{article.slug}",
            _ladder(subject, title_words[-1] if title_words else "", "handmade ceramics"),
            [Slot(article.cover_image, "landscape", article.title)],
        ))

    return groups


def build_groups() -> list[Group]:
    """Every group, with duplicate names dropped.

    Categories and collections share tile names (`collection-ceramics` is both
    a category hero and a collection hero), so the first group to claim a name
    keeps it and later ones silently skip it.
    """
    seen: set[str] = set()
    groups: list[Group] = []
    for group in _catalogue() + _editorial():
        slots = [slot for slot in group.slots if slot.name not in seen]
        seen.update(slot.name for slot in slots)
        if slots:
            groups.append(Group(group.key, group.queries, slots))
    return groups


def all_slots() -> list[Slot]:
    return [slot for group in build_groups() for slot in group.slots]


def ratio_for(name: str) -> str:
    for slot in all_slots():
        if slot.name == name:
            return slot.ratio
    return DEFAULT_RATIO
