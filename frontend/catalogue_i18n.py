"""Chinese presentation copy for seeded catalogue records."""

from __future__ import annotations

from copy import copy

from django.utils.translation import get_language, gettext, pgettext

from frontend.mockdata.collections import CATEGORIES, COLLECTIONS, EXTRA_COLLECTIONS
from frontend.mockdata.faqs import FAQ_GROUPS_BY_SLUG
from frontend.mockdata.journal import ARTICLES_BY_SLUG
from frontend.mockdata.makers import MAKERS_BY_SLUG
from frontend.mockdata.products import PRODUCTS, PRODUCTS_BY_SLUG

_SEEDED_COLOUR_LABELS = frozenset(
    variant["label"] for product in PRODUCTS for variant in product["variants"]
    if variant["group"] == "colour"
)


def localize_colour_label(label: str) -> str:
    """Translate a recognised colour for display without changing its stored label."""
    return gettext(label) if label in _SEEDED_COLOUR_LABELS else label


def localize_size_label(label: str) -> str:
    """Translate seeded named sizes for display; preserve measurements and custom labels."""
    if label == "Medium":
        return pgettext("product size", "Medium")
    if label == "Large":
        return pgettext("product size", "Large")
    return label


def _is_chinese() -> bool:
    return (get_language() or "").lower().startswith("zh")


def is_chinese() -> bool:
    return _is_chinese()


def localize_collection(collection):
    if not _is_chinese():
        return collection

    if collection.kind == "category":
        source = next((item for item in CATEGORIES if item["slug"] == collection.slug), None)
    elif collection.kind == "editorial":
        source = next(
            (item for item in COLLECTIONS
             if item["kind"] == "editorial" and item["slug"] == collection.slug),
            None,
        )
        if source is None:
            source = next(
                (item for item in EXTRA_COLLECTIONS if item["slug"] == collection.slug),
                None,
            )
    else:
        return collection
    if source is None:
        return collection

    localized = copy(collection)
    english_name = source["title"] if "title" in source else source["name"]
    for field, english in (("name", english_name), ("tagline", source["tagline"]),
                           ("description", source["description"])):
        current = getattr(collection, field)
        if current == english:
            value = (pgettext("category", "Home")
                     if field == "name" and collection.kind == "category"
                     and collection.slug == "home" else gettext(current))
            setattr(localized, field, value)
    return localized


def localize_maker(maker):
    if not _is_chinese():
        return maker
    source = MAKERS_BY_SLUG.get(maker.slug)
    if source is None:
        return maker

    localized = copy(maker)
    for field in ("name", "discipline", "location", "tagline"):
        current = getattr(maker, field)
        if current == source[field]:
            setattr(localized, field, gettext(current))

    for field in ("biography", "process"):
        current = getattr(maker, field)
        if current == source[field]:
            setattr(localized, field, [gettext(value) for value in current])

    canonical_short_bio = source["biography"][0] if source["biography"] else ""
    if maker.short_bio and maker.short_bio == canonical_short_bio:
        localized.short_bio = gettext(maker.short_bio)
    return localized


def localize_product(product):
    if not _is_chinese():
        return product
    source = PRODUCTS_BY_SLUG.get(product.slug)
    if source is None:
        return product
    localized = copy(product)
    fields = (
        ("name", "name"),
        ("short_description", "short_description"),
        ("description", "description"),
        ("story", "story"),
        ("care_instructions", "care"),
        ("shipping_information", "dispatch"),
    )
    for field, source_field in fields:
        current = getattr(product, field)
        if current == source[source_field]:
            setattr(localized, field, gettext(current))
    return localized


class _LocalizedFAQGroup:
    """Presentation wrapper for the model's read-only ``items`` property."""

    def __init__(self, source, *, title, blurb, items):
        self._source = source
        self.title = title
        self.blurb = blurb
        self.items = items

    def __getattr__(self, name):
        return getattr(self._source, name)

    def __str__(self):
        return str(self._source)


def _active_faq_items(group):
    prefetched = getattr(group, "_prefetched_objects_cache", {}).get("faqs")
    items = prefetched if prefetched is not None else group.items
    return [item for item in items if item.is_active]


def localize_faq_group(group):
    if not _is_chinese():
        return group
    source = FAQ_GROUPS_BY_SLUG.get(group.slug)
    if source is None:
        return group

    title = gettext(group.title) if group.title == source["title"] else group.title
    blurb = gettext(group.blurb) if group.blurb == source["blurb"] else group.blurb
    items = _active_faq_items(group)
    localized_items = items
    if len(items) == len(source["items"]):
        localized_items = []
        for item, canonical in zip(items, source["items"], strict=True):
            localized = copy(item)
            if item.question == canonical["q"]:
                localized.question = gettext(item.question)
            if item.answer == canonical["a"]:
                localized.answer = gettext(item.answer)
            localized_items.append(localized)

    return _LocalizedFAQGroup(
        group, title=title, blurb=blurb, items=localized_items,
    )


def localize_article(article):
    if not is_chinese() or not article:
        return article
    source = ARTICLES_BY_SLUG.get(article.slug)
    if source is None:
        return article

    values = {}
    for field in ("title", "standfirst", "category", "read_time", "author"):
        current = getattr(article, field)
        values[field] = gettext(current) if current == source[field] else current

    body = article.body
    canonical_body = source["body"]
    structure_matches = (
        isinstance(body, list)
        and len(body) == len(canonical_body)
        and all(
            isinstance(block, dict) and block.get("type") == canonical.get("type")
            for block, canonical in zip(body, canonical_body, strict=True)
        )
    )
    canonical_texts = {block["text"] for block in canonical_body}
    has_relocated_text = structure_matches and any(
        block.get("text") != canonical["text"]
        and block.get("text") in canonical_texts
        for block, canonical in zip(body, canonical_body, strict=True)
    )
    if structure_matches and not has_relocated_text:
        body = []
        for block, canonical in zip(article.body, canonical_body, strict=True):
            localized_block = dict(block)
            if block.get("text") == canonical["text"]:
                localized_block["text"] = gettext(block["text"])
            body.append(localized_block)

    return _LocalizedArticle(article, body=body, **values)


class _LocalizedArticle:
    """Read-only presentation wrapper for localised article fields and date."""

    def __init__(self, source, *, title, standfirst, category, read_time, author, body):
        self._source = source
        self.title = title
        self.standfirst = standfirst
        self.excerpt = standfirst
        self.category = category
        self.read_time = read_time
        self.author = author
        self.body = body
        published = source.published_at
        self.date = f"{published.year}年{published.month}月{published.day}日"

    def __getattr__(self, name):
        return getattr(self._source, name)

    def __str__(self):
        return self.title
